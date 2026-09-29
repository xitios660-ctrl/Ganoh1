"""One-shot cross-store routing verification for GANOH production."""
import json, os, sys, time, uuid
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from pymongo import MongoClient

ROOT="http://127.0.0.1:"+os.environ.get("PORT","10000")
MONGO_URL=os.environ["MONGO_URL"]
DB_NAME=os.environ.get("DB_NAME","ganoh_production")
MARKER="E2E_ROUTE_"+uuid.uuid4().hex[:8]

def req(method,path,data=None):
    body=json.dumps(data).encode() if data is not None else None
    headers={"Accept":"application/json"}
    if body is not None: headers["Content-Type"]="application/json"
    with urlopen(Request(ROOT+path,data=body,headers=headers,method=method),timeout=15) as r:
        raw=r.read()
        return json.loads(raw) if raw else {}

def has_id(payload, oid):
    return any(x.get("id")==oid for x in payload.get("orders",[]))

def main():
    client=MongoClient(MONGO_URL,serverSelectionTimeoutMS=10000)
    db=client[DB_NAME]
    created=[]
    snapshots=[]
    try:
        for _ in range(60):
            try:
                if req("GET","/healthz").get("status")=="ok": break
            except Exception:
                time.sleep(2)
        else:
            raise RuntimeError("health unavailable")

        menus={}
        for store in ("runner","gym-londres"):
            menu=req("GET",f"/api/menu/{store}")
            if not menu.get("items"): raise AssertionError(f"{store} menu empty")
            item=menu["items"][0]
            item_id=str(item["id"]).split("-")[0]
            snap=db.stock.find_one({"store":store,"menu_item_id":item_id})
            snapshots.append((store,item_id,snap))
            menus[store]=item

        orders={}
        for store,label in (("runner","RUNNER"),("gym-londres","LONDRES")):
            item=menus[store]
            order=req("POST","/api/orders",{
                "store":store,
                "customer_name":f"{MARKER}_{label}",
                "items":[{
                    "menu_item_id":item["id"],
                    "name":item["name"],
                    "price":float(item["price"]),
                    "quantity":1
                }],
                "total":float(item["price"]),
                "payment_method":"cash",
                "pickup_time":"ROUTING_TEST"
            })
            created.append((store,order["id"]))
            orders[store]=order["id"]

        runner=req("GET","/api/orders/runner")
        londres=req("GET","/api/orders/gym-londres")

        assert has_id(runner,orders["runner"]), "Runner order missing from Runner kitchen"
        assert not has_id(runner,orders["gym-londres"]), "Londres order leaked into Runner kitchen"
        assert has_id(londres,orders["gym-londres"]), "Londres order missing from Londres kitchen"
        assert not has_id(londres,orders["runner"]), "Runner order leaked into Londres kitchen"

        # Store-scoped tracking must also reject the other store's order.
        wrong_ok=False
        try:
            req("GET",f"/api/orders/runner/{orders['gym-londres']}")
        except HTTPError as exc:
            wrong_ok=(exc.code==404)
        assert wrong_ok, "Runner route could read Londres order"

        wrong_ok=False
        try:
            req("GET",f"/api/orders/gym-londres/{orders['runner']}")
        except HTTPError as exc:
            wrong_ok=(exc.code==404)
        assert wrong_ok, "Londres route could read Runner order"

        print("STORE ROUTING PASS: Runner -> Runner only; Londres -> Londres only",flush=True)
    finally:
        for store,oid in created:
            db.orders.delete_many({"id":oid,"store":store})
            db.order_history.delete_many({"id":oid,"store":store})
        for store,item_id,snap in snapshots:
            if snap is None:
                db.stock.delete_many({"store":store,"menu_item_id":item_id})
            else:
                restore={k:v for k,v in snap.items() if k!="_id"}
                db.stock.replace_one({"store":store,"menu_item_id":item_id},restore,upsert=True)
        leftovers=db.orders.count_documents({"customer_name":{"$regex":f"^{MARKER}"}})
        if leftovers:
            raise RuntimeError(f"routing cleanup left {leftovers} orders")
        print("STORE ROUTING CLEANUP PASS",flush=True)
        client.close()

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("STORE ROUTING FAILED: "+str(e)[:400],file=sys.stderr,flush=True)
        sys.exit(1)
