package com.ganoh.tv;

import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import javax.net.ssl.HttpsURLConnection;

/** No database credentials, redirects, cleartext, telemetry, or financial writes. */
final class CentralClient {
    static final String BASE="/api/sync/v1/tv/";
    interface Connector { HttpsURLConnection open(URL url) throws IOException; }
    static final class AccessDenied extends IOException { AccessDenied(){super("Sessão encerrada ou acesso recusado. Entre novamente.");} }
    private final String origin;
    private final Connector connector;
    CentralClient(String origin) { this(origin,url -> (HttpsURLConnection)url.openConnection()); }
    CentralClient(String origin, Connector connector) { this.origin=origin(origin);this.connector=connector; }
    static String origin(String input) {
        try {
            URI uri=new URI(input.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || uri.getHost()==null || uri.getRawUserInfo()!=null
                    || uri.getRawQuery()!=null || uri.getRawFragment()!=null
                    || !(uri.getRawPath().isEmpty() || "/".equals(uri.getRawPath()))
                    || (uri.getPort()!=-1 && uri.getPort()!=443)) throw new IllegalArgumentException();
            return "https://"+uri.getHost().toLowerCase(java.util.Locale.ROOT);
        } catch (Exception error) { throw new IllegalArgumentException("Informe somente a origem HTTPS de homologação, sem caminho, senha ou parâmetros."); }
    }
    JSONObject login(String username,String password) throws Exception {
        if (username.length()<3 || username.length()>64 || password.length()<12 || password.length()>256)
            throw new IllegalArgumentException("Informe usuário e senha exclusivos da TV na homologação.");
        JSONObject result=request("login",null,new JSONObject().put("username",username).put("password",password));
        if (!"tv:read".equals(result.optString("scope"))) throw new IOException("Servidor não emitiu sessão exclusiva de consulta TV.");
        return result;
    }
    Dashboard overview(String token) throws Exception { return Dashboard.parse(request("overview",token,null)); }
    JSONObject stock(String token,String unit,String cursor) throws Exception {
        Dashboard.unitName(unit);
        String path="stock?unit="+unit;
        if (cursor!=null) {
            if (!cursor.matches("[0-9a-f-]{36}:[0-9]{1,4}")) throw new IOException("Cursor de estoque inválido");
            path += "&cursor="+java.net.URLEncoder.encode(cursor,"UTF-8");
        }
        return request(path,token,null);
    }
    void logout(String token) throws Exception { request("logout",token,new JSONObject()); }
    private JSONObject request(String path,String token,JSONObject body) throws Exception {
        // All methods are private except the four explicit TV-view operations.
        HttpsURLConnection connection=connector.open(new URL(origin+BASE+path));
        try {
            connection.setInstanceFollowRedirects(false); connection.setConnectTimeout(8000); connection.setReadTimeout(8000);
            connection.setUseCaches(false);connection.setRequestProperty("Accept","application/json");
            connection.setRequestProperty("Cache-Control","no-store");
            if (token!=null) {
                if (!token.matches("[A-Za-z0-9_-]{20,512}")) throw new IOException("Sessão inválida");
                connection.setRequestProperty("Authorization","Bearer "+token);
            }
            connection.setRequestMethod(body==null?"GET":"POST");
            if (body!=null) {
                connection.setDoOutput(true);connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
                byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8); connection.setFixedLengthStreamingMode(bytes.length);
                try (OutputStream out=connection.getOutputStream()) {out.write(bytes);}
            }
            int status=connection.getResponseCode();
            if (status==401 || status==403) throw new AccessDenied();
            if (status<200 || status>=300) throw new IOException("Central indisponível. Nenhum redirecionamento foi seguido.");
            String type=connection.getContentType();
            if (type==null || !type.toLowerCase(java.util.Locale.ROOT).startsWith("application/json")) throw new IOException("Resposta incompatível da central.");
            try (InputStream input=connection.getInputStream(); ByteArrayOutputStream out=new ByteArrayOutputStream()) {
                byte[] buffer=new byte[8192];int read;
                while ((read=input.read(buffer))!=-1) {if (out.size()+read>1_048_576) throw new IOException("Resposta excede o limite de segurança.");out.write(buffer,0,read);}
                return new JSONObject(out.toString("UTF-8"));
            }
        } finally {connection.disconnect();}
    }
}
