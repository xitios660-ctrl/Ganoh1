package com.ganoh.tv;
import org.json.JSONObject;
import org.json.JSONArray;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28)
public class StockPageTest {
    static final String ID="8b1358fa-b0ca-4c74-bc27-c45f275b5f77";
    static JSONObject page(int offset,int count,boolean done) throws Exception {
        JSONArray items=new JSONArray();for(int i=offset;i<offset+count;i++)items.put(new JSONObject().put("sku","item-"+i).put("name","Produto "+i).put("quantity",7).put("version",2));
        return new JSONObject().put("unit","runner").put("generation",ID).put("created_at","2026-11-20T12:00:00Z")
                .put("includes_unsynced_local_data",false).put("items",items).put("done",done).put("next_cursor",done?JSONObject.NULL:ID+":"+(offset+count));
    }
    @Test public void paginatedSnapshotIsImmutableAndScoped() throws Exception {
        StockPage p=new StockPage("runner");p.append(page(0,100,false));assertEquals(ID+":100",p.nextCursor);
        p.append(page(100,2,true));assertTrue(p.done);assertEquals(102,p.lines.size());
    }
    @Test public void malformedPageNeverOverwritesPreviousData() throws Exception {
        StockPage p=new StockPage("runner");p.append(page(0,100,false));
        JSONObject wrong=page(100,1,true).put("unit","gym-londres");assertThrows(Exception.class,()->p.append(wrong));
        JSONObject changed=page(100,1,true).put("generation","aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");assertThrows(Exception.class,()->p.append(changed));
        assertThrows(Exception.class,()->p.append(page(0,1,true)));assertEquals(100,p.lines.size());assertFalse(p.done);
    }
    @Test public void noInfinitePaginationOrNegativeStock() throws Exception {
        StockPage p=new StockPage("runner");JSONObject b=page(0,100,false).put("next_cursor",ID+":0");
        assertThrows(Exception.class,()->p.append(b));assertTrue(p.lines.isEmpty());
        JSONObject c=page(0,1,true);c.getJSONArray("items").getJSONObject(0).put("quantity",-1);
        assertThrows(Exception.class,()->p.append(c));assertTrue(p.lines.isEmpty());
    }
}
