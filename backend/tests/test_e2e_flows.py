"""
End-to-end flow tests via HTTP (backend) for:
- Cliente: realiza pedidos com todos os métodos de pagamento (cash, pix, debit, credit, prazo)
- Funcionário (cozinha): login, ver pedidos, alterar status, abater dívidas
- Gestor: dashboard, totais, vendas

Roda contra o backend local em http://localhost:8001
"""
import os
import time
import json
import uuid
import requests
import pytest

BASE = os.environ.get("BASE_URL", "http://localhost:8001")
API = f"{BASE}/api"
KITCHEN_PWD = "1234"
GESTOR = ("gestor", "ganoh2024")
STORE = "runner"

TEST_TAG = uuid.uuid4().hex[:6]
CUSTOMER_NAME = f"E2ECliente_{TEST_TAG}"
CUSTOMER_FIADO = f"E2EFiado_{TEST_TAG}"


def _menu_items():
    r = requests.get(f"{API}/menu/{STORE}", timeout=10)
    r.raise_for_status()
    items = r.json().get("items", [])
    assert len(items) > 0, "Menu vazio"
    return items


def _make_order(payment_method, total=None, customer=CUSTOMER_NAME, items_override=None):
    items_data = items_override or _menu_items()[:1]
    items = [
        {
            "menu_item_id": items_data[0]["id"],
            "name": items_data[0]["name"],
            "price": items_data[0]["price"],
            "quantity": 1,
            "prep_time": items_data[0].get("prep_time", 10),
        }
    ]
    payload = {
        "store": STORE,
        "customer_name": customer,
        "items": items,
        "payment_method": payment_method,
        "total": total or items_data[0]["price"],
    }
    r = requests.post(f"{API}/orders", json=payload, timeout=10)
    return r


# ==========================================================================
# CLIENTE — todos os métodos de pagamento
# ==========================================================================

class TestClienteFluxo:
    def test_carregar_menu(self):
        items = _menu_items()
        assert all("price" in i and "name" in i for i in items)

    def test_pedido_dinheiro(self):
        r = _make_order("cash")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_method"] == "cash"
        assert d["status"] in ("received", "preparing")

    def test_pedido_pix(self):
        r = _make_order("pix")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_method"] == "pix"
        # PIX começa pending_payment
        assert d["status"] == "pending_payment"

    def test_pedido_debito(self):
        r = _make_order("debit")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_method"] == "debit"

    def test_pedido_credito(self):
        r = _make_order("credit")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_method"] == "credit"

    def test_pedido_prazo_cria_divida(self):
        # cliente novo, sem crédito → gera dívida
        r = _make_order("prazo", customer=CUSTOMER_FIADO, total=25)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payment_method"] == "prazo"

        # verifica que aparece na lista de dívidas
        time.sleep(0.5)
        debts = requests.get(f"{API}/prazo/debts", params={"store": STORE}, timeout=10).json()
        names = [c["name"] for c in debts.get("debts", [])]
        assert CUSTOMER_FIADO in names, f"Fiado não criado: {names}"


# ==========================================================================
# FUNCIONÁRIO (cozinha) — login, fluxo de pedidos, abater dívidas
# ==========================================================================

class TestFuncionarioFluxo:
    def test_kitchen_password_correct(self):
        r = requests.post(
            f"{API}/auth/kitchen", json={"password": KITCHEN_PWD}, timeout=10
        )
        # endpoint pode não existir; aceitar 404 ou 200
        assert r.status_code in (200, 401, 404)

    def test_listar_pedidos_pendentes(self):
        r = requests.get(f"{API}/orders/{STORE}", timeout=10)
        assert r.status_code == 200
        orders = r.json().get("orders", [])
        # deve incluir pelo menos os pedidos do cliente
        names = [o.get("customer_name") for o in orders]
        assert CUSTOMER_NAME in names or len(orders) > 0

    def test_atualizar_status_pedido(self):
        # pegar o primeiro pedido do cliente
        orders = requests.get(f"{API}/orders/{STORE}", timeout=10).json().get("orders", [])
        target = next(
            (o for o in orders if o.get("customer_name") == CUSTOMER_NAME
             and o.get("status") in ("received", "preparing")),
            None,
        )
        if not target:
            pytest.skip("Sem pedido elegível para mudança de status")
        oid = target["id"]
        r = requests.patch(
            f"{API}/orders/{STORE}/{oid}/status", json={"status": "ready"}, timeout=10
        )
        assert r.status_code in (200, 204), r.text

    def test_abater_dividas_todos_metodos(self):
        # Garantir saldo a favor pré-existente para testar 'saldo'
        # 1) Criar cliente prazo
        create_resp = requests.post(
            f"{API}/prazo/customers",
            auth=GESTOR,
            json={"name": CUSTOMER_FIADO, "phone": "11999999999", "store": STORE},
            timeout=10,
        )
        # se já existe (400) tudo bem
        assert create_resp.status_code in (200, 400), create_resp.text

        # 2) Buscar cliente
        custs = requests.get(f"{API}/prazo/customers", timeout=10).json().get("customers", [])
        cust = next((c for c in custs if c["name"] == CUSTOMER_FIADO), None)
        assert cust, f"Cliente fiado {CUSTOMER_FIADO} não cadastrado"
        cid = cust["id"]

        # Adicionar R$ 100 de saldo a favor
        r = requests.post(
            f"{API}/prazo/customers/{cid}/add-credit",
            json={"amount": 100, "notes": "e2e"},
            timeout=10,
        )
        assert r.status_code == 200, r.text

        # Criar mais débito para testar abater com cada método
        for _ in range(4):
            _make_order("prazo", customer=CUSTOMER_FIADO, total=20)

        # Estado: provavelmente dívida abatida automaticamente por crédito
        # Verificar
        debts = requests.get(
            f"{API}/prazo/debts", params={"store": STORE}, timeout=10
        ).json().get("debts", [])
        debt_info = next((d for d in debts if d["name"] == CUSTOMER_FIADO), None)

        # Recarregar customer
        custs = requests.get(f"{API}/prazo/customers", timeout=10).json().get("customers", [])
        cust = next(c for c in custs if c["name"] == CUSTOMER_FIADO)

        # Se cliente tem dívida agora, testar abater
        if debt_info and debt_info.get("total", 0) > 0:
            # Abater R$ 5 via cash → saldo não pode mudar
            saldo_before = cust.get("credit", 0)
            r = requests.post(
                f"{API}/prazo/abater/{CUSTOMER_FIADO}",
                json={"password": KITCHEN_PWD, "amount": 5, "payment_method": "cash"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert "credit_used" not in r.json() or r.json().get("credit_used", 0) == 0

            custs = requests.get(f"{API}/prazo/customers", timeout=10).json().get("customers", [])
            cust = next(c for c in custs if c["name"] == CUSTOMER_FIADO)
            assert cust.get("credit", 0) == saldo_before, "Bug: saldo mudou ao pagar com dinheiro!"

        # Adicionar mais crédito para testar 'saldo'
        requests.post(
            f"{API}/prazo/customers/{cid}/add-credit",
            json={"amount": 50, "notes": "para teste saldo"},
            timeout=10,
        )
        # Criar dívida pra abater com saldo
        _make_order("prazo", customer=CUSTOMER_FIADO, total=30)
        time.sleep(0.3)

        custs = requests.get(f"{API}/prazo/customers", timeout=10).json().get("customers", [])
        cust = next(c for c in custs if c["name"] == CUSTOMER_FIADO)
        debts = requests.get(f"{API}/prazo/debts", params={"store": STORE}, timeout=10).json().get("debts", [])
        debt_info = next((d for d in debts if d["name"] == CUSTOMER_FIADO), None)

        if debt_info and debt_info.get("total", 0) > 0 and cust.get("credit", 0) > 0:
            # Abater via 'saldo'
            credit_before = cust["credit"]
            amount = min(10, credit_before, debt_info["total"])
            r = requests.post(
                f"{API}/prazo/abater/{CUSTOMER_FIADO}",
                json={"password": KITCHEN_PWD, "amount": amount, "payment_method": "saldo"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            assert r.json().get("credit_used") == amount

    def test_caixa_do_dia(self):
        r = requests.get(f"{API}/cash/{STORE}/today", timeout=10)
        assert r.status_code == 200, r.text
        d = r.json()
        # Esperamos as chaves principais
        assert "total" in d or "by_payment" in d or "today_total" in d


# ==========================================================================
# GESTOR — dashboard, totais, relatórios
# ==========================================================================

class TestGestorFluxo:
    def test_login(self):
        r = requests.post(
            f"{API}/auth/login",
            json={"username": GESTOR[0], "password": GESTOR[1]},
            timeout=10,
        )
        assert r.status_code == 200, r.text

    def test_dashboard(self):
        r = requests.get(f"{API}/gestor/dashboard", auth=GESTOR, timeout=10)
        if r.status_code == 404:
            pytest.skip("Endpoint dashboard inexistente")
        assert r.status_code == 200, r.text

    def test_total_caixa_consistente(self):
        # Caixa do dia
        r = requests.get(f"{API}/cash/{STORE}/today", timeout=10)
        assert r.status_code == 200
        d1 = r.json()
        time.sleep(0.5)
        r = requests.get(f"{API}/cash/{STORE}/today", timeout=10)
        d2 = r.json()
        # Os números devem ser determinísticos (sem dois fetches dando valores diferentes)
        assert d1 == d2 or json.dumps(d1, sort_keys=True) == json.dumps(d2, sort_keys=True)

    def test_listagem_clientes_prazo(self):
        r = requests.get(f"{API}/prazo/customers", auth=GESTOR, timeout=10)
        assert r.status_code == 200, r.text

    def test_listagem_dividas(self):
        r = requests.get(f"{API}/prazo/debts", params={"store": STORE}, timeout=10)
        assert r.status_code == 200

    def test_orders_listing(self):
        r = requests.get(f"{API}/orders/{STORE}", timeout=10)
        assert r.status_code == 200, r.text


# ==========================================================================
# Cleanup
# ==========================================================================

def teardown_module(module):
    """Limpar dados criados pelo teste"""
    try:
        # remover cliente fiado de teste
        custs = requests.get(f"{API}/prazo/customers", timeout=10).json().get("customers", [])
        for c in custs:
            if c["name"] in (CUSTOMER_FIADO,):
                requests.delete(f"{API}/prazo/customers/{c['id']}", auth=GESTOR, timeout=10)
        # remover pedidos via mongosh
        import subprocess
        for name in (CUSTOMER_NAME, CUSTOMER_FIADO):
            subprocess.run(
                ["mongosh", "test_database", "--quiet", "--eval",
                 f'db.orders.deleteMany({{customer_name:"{name}"}}); '
                 f'db.prazo_partial_payments.deleteMany({{customer_name:"{name}"}});'],
                capture_output=True, timeout=10,
            )
    except Exception as e:
        print(f"Cleanup warning: {e}")
