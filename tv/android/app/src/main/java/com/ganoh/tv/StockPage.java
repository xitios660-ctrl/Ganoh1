package com.ganoh.tv;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class StockPage {
    final String unit;
    String generation, createdAt, nextCursor;
    boolean done;
    final List<String> lines=new ArrayList<>();
    private final Set<String> skus=new HashSet<>();
    StockPage(String unit) {Dashboard.unitName(unit);this.unit=unit;}
    void append(JSONObject body) throws JSONException {
        if (done) throw new JSONException("Snapshot já concluído");
        if (!unit.equals(body.getString("unit")) || body.getBoolean("includes_unsynced_local_data")) throw new JSONException("Escopo do estoque divergente");
        String id=body.getString("generation");
        if (!id.matches("[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}") || (generation!=null && !generation.equals(id)))
            throw new JSONException("Geração de estoque divergente");
        JSONArray items=body.getJSONArray("items");boolean complete=body.getBoolean("done");
        if (items.length()>100 || lines.size()+items.length()>1000 || (!complete && items.length()!=100)) throw new JSONException("Página de estoque inválida");
        String next=complete?null:body.getString("next_cursor");
        if (!complete && !(id+":"+(lines.size()+items.length())).equals(next)) throw new JSONException("Cursor de estoque divergente");
        Set<String> incoming=new HashSet<>();List<String> addition=new ArrayList<>();
        for (int i=0;i<items.length();i++) {
            JSONObject item=items.getJSONObject(i);String sku=item.getString("sku");
            if (sku.length()>200 || skus.contains(sku) || !incoming.add(sku)) throw new JSONException("SKU duplicado ou inválido");
            long quantity=Dashboard.cents(item,"quantity"),version=Dashboard.cents(item,"version");
            if (quantity<0 || version<1) throw new JSONException("Estoque inválido");
            addition.add(item.optString("name",sku)+"  •  "+quantity+" un.  •  versão "+version);
        }
        String created=body.getString("created_at");
        if (created.length()>64 || (createdAt!=null && !createdAt.equals(created))) throw new JSONException("Data do snapshot divergente");
        // Commit the complete page only after all fields have been checked.
        lines.addAll(addition);skus.addAll(incoming);generation=id;createdAt=created;nextCursor=next;done=complete;
    }
}
