package com.ganoh.tv;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28)
public class DashboardTest {
    static JSONObject body() throws Exception {
        Dashboard demo=Dashboard.demo();org.json.JSONArray rows=new org.json.JSONArray();for(JSONObject row:demo.units)rows.put(new JSONObject(row.toString()));
        return new JSONObject().put("scope","CONFIRMED_ISOLATED_V1_LEDGER").put("includes_unsynced_local_data",false)
                .put("legacy_production_integrated",false).put("generated_at","2026-11-20T12:00:00Z")
                .put("consolidated",new JSONObject(demo.total.toString())).put("units",rows);
    }
    @Test public void confirmedTotalsAreScopedAndCentsExact() throws Exception {
        Dashboard d=Dashboard.parse(body());assertEquals(2,d.units.size());assertEquals(212000,d.total.getLong("revenue_cents"));
        assertEquals(176000,d.total.getLong("result_cents"));assertEquals("GYM LONDRES",Dashboard.unitName("gym-londres"));
        assertTrue(Dashboard.money(1001).contains("10,01"));
    }
    @Test public void rejectsProductionUnconfirmedOrWrongTotals() throws Exception {
        JSONObject b=body();b.put("legacy_production_integrated",true);assertThrows(Exception.class,()->Dashboard.parse(b));
        b.put("legacy_production_integrated",false).put("includes_unsynced_local_data",true);assertThrows(Exception.class,()->Dashboard.parse(b));
        b.put("includes_unsynced_local_data",false);b.getJSONObject("consolidated").put("cash_cents",1);assertThrows(Exception.class,()->Dashboard.parse(b));
    }
    @Test public void rejectsUnitLeakDuplicateAndClaimedOfflineCounts() throws Exception {
        JSONObject b=body();b.getJSONArray("units").getJSONObject(1).put("unit","runner");assertThrows(Exception.class,()->Dashboard.parse(b));
        JSONObject c=body();c.getJSONArray("units").getJSONObject(0).put("local_pending",0);assertThrows(Exception.class,()->Dashboard.parse(c));
        assertThrows(IllegalArgumentException.class,()->Dashboard.unitName("other-store"));
    }
    @Test public void rejectsFractionalAndOverflowingMoney() throws Exception {
        assertThrows(Exception.class,()->Dashboard.cents(new JSONObject().put("v",1.25),"v"));
        assertThrows(Exception.class,()->Dashboard.cents(new JSONObject().put("v",Long.MIN_VALUE),"v"));
        assertThrows(Exception.class,()->Dashboard.cents(new JSONObject().put("v","100"),"v"));
    }
}
