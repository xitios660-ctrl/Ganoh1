package com.ganoh.tv;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/** Only the confirmed, isolated v1 ledger is accepted. No legacy/production fallback. */
final class Dashboard {
    static final String[] MONEY = {"revenue_cents", "expense_cents", "cash_cents", "receivable_cents", "cash_variance_cents"};
    final JSONObject total;
    final List<JSONObject> units;
    final String generatedAt;
    final long receivedAt;
    Dashboard(JSONObject total, List<JSONObject> units, String generatedAt) {
        this.total = total; this.units = Collections.unmodifiableList(units);
        this.generatedAt = generatedAt; this.receivedAt = android.os.SystemClock.elapsedRealtime();
    }
    static String unitName(String unit) {
        if ("runner".equals(unit)) return "RUNNER";
        if ("gym-londres".equals(unit)) return "GYM LONDRES";
        throw new IllegalArgumentException("Unidade inválida");
    }
    static long cents(JSONObject object, String key) throws JSONException {
        Object value = object.get(key);
        if (!(value instanceof Integer || value instanceof Long)) throw new JSONException("Valor monetário inválido");
        long result = ((Number)value).longValue();
        if (result < -9_000_000_000_000L || result > 9_000_000_000_000L) throw new JSONException("Valor monetário fora do limite");
        return result;
    }
    static String money(long cents) {
        return java.text.NumberFormat.getCurrencyInstance(new Locale("pt", "BR")).format(java.math.BigDecimal.valueOf(cents, 2));
    }
    static Dashboard parse(JSONObject body) throws JSONException {
        if (!"CONFIRMED_ISOLATED_V1_LEDGER".equals(body.getString("scope"))
                || body.getBoolean("includes_unsynced_local_data") || body.getBoolean("legacy_production_integrated"))
            throw new JSONException("Servidor incompatível com homologação isolada");
        JSONObject total = body.getJSONObject("consolidated");
        JSONArray rows = body.getJSONArray("units");
        if (rows.length() > 2) throw new JSONException("Escopo de unidades inválido");
        Set<String> seen = new HashSet<>(); List<JSONObject> units = new ArrayList<>();
        long[] sums = new long[MONEY.length];
        for (int i=0; i<rows.length(); i++) {
            JSONObject row=rows.getJSONObject(i); String unit=row.getString("unit"); unitName(unit);
            if (!seen.add(unit) || !row.has("local_pending") || !row.isNull("local_pending"))
                throw new JSONException("Escopo ou pendências incompatíveis");
            row.getBoolean("stale");
            for (int k=0; k<MONEY.length; k++) sums[k] += cents(row,MONEY[k]);
            units.add(row);
        }
        for (int k=0; k<MONEY.length; k++) if (cents(total,MONEY[k]) != sums[k]) throw new JSONException("Consolidado divergente");
        if (cents(total,"result_cents") != sums[0]-sums[1]-sums[4]) throw new JSONException("Resultado divergente");
        String generated=body.getString("generated_at");
        if (generated.length()>64 || generated.length()<20) throw new JSONException("Data central inválida");
        return new Dashboard(total,units,generated);
    }
    static Dashboard demo() {
        try {
            JSONArray units=new JSONArray(); JSONObject total=new JSONObject();
            for (String key:MONEY) total.put(key,0);
            for (int i=0;i<2;i++) {
                JSONObject row=new JSONObject().put("unit",i==0?"runner":"gym-londres")
                        .put("revenue_cents",i==0?125000:87000).put("expense_cents",i==0?21000:15000)
                        .put("cash_cents",i==0?94000:66000).put("receivable_cents",i==0?10000:6000)
                        .put("cash_variance_cents",0).put("stale",i==1).put("last_sync_at","Exemplo fictício")
                        .put("local_pending",JSONObject.NULL).put("conflicts",0).put("cash_reviews",0);
                for (String key:MONEY) total.put(key,total.getLong(key)+row.getLong(key)); units.put(row);
            }
            total.put("result_cents",176000);
            return parse(new JSONObject().put("scope","CONFIRMED_ISOLATED_V1_LEDGER").put("includes_unsynced_local_data",false)
                    .put("legacy_production_integrated",false).put("generated_at","2026-01-01T00:00:00Z")
                    .put("consolidated",total).put("units",units));
        } catch (JSONException impossible) { throw new IllegalStateException(impossible); }
    }
}
