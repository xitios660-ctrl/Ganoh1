package com.ganoh.tv;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import java.io.*;
import java.net.URL;
import java.security.cert.Certificate;
import javax.net.ssl.HttpsURLConnection;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28)
public class CentralClientTest {
    static final String TOKEN="fixture-session-not-real-1234567890";
    static class Connection extends HttpsURLConnection {
        int code=200;byte[] payload="{}".getBytes(java.nio.charset.StandardCharsets.UTF_8);boolean closed;
        final ByteArrayOutputStream sent=new ByteArrayOutputStream();
        Connection(URL url){super(url);}
        public String getCipherSuite(){return "test-only";}public Certificate[] getLocalCertificates(){return null;}public Certificate[] getServerCertificates(){return new Certificate[0];}
        public void connect(){} public boolean usingProxy(){return false;}public void disconnect(){closed=true;}
        public int getResponseCode(){return code;}public String getContentType(){return "application/json";}
        public InputStream getInputStream(){return new ByteArrayInputStream(payload);}public OutputStream getOutputStream(){return sent;}
    }
    @Test public void originNeverAcceptsCleartextCredentialsOrPaths(){
        assertEquals("https://central.example",CentralClient.origin("https://CENTRAL.example:443/"));
        for(String invalid:new String[]{"http://central.example","https://owner:password@central.example","https://central.example/path","https://central.example?token=x","https://central.example/#token","https://central.example:8080","https:///missing","javascript:alert(1)"})
            assertThrows(IllegalArgumentException.class,()->CentralClient.origin(invalid));
    }
    @Test public void refusesRedirectAndClosesConnection() throws Exception {
        final Connection[] actual={null};CentralClient c=new CentralClient("https://central.example",url->{actual[0]=new Connection(url);actual[0].code=302;return actual[0];});
        assertThrows(IOException.class,()->c.overview(TOKEN));assertFalse(actual[0].getInstanceFollowRedirects());assertTrue(actual[0].closed);
        assertEquals("/api/sync/v1/owner/overview",actual[0].getURL().getPath());assertEquals("GET",actual[0].getRequestMethod());
    }
    @Test public void loginIsOnlyCredentialWriteAndNeverChangesMoney() throws Exception {
        final Connection[] actual={null};CentralClient c=new CentralClient("https://central.example",url->{actual[0]=new Connection(url);return actual[0];});
        c.login("fixture-owner","Fixture-Password-2026");assertEquals("POST",actual[0].getRequestMethod());
        assertEquals("/api/sync/v1/owner/login",actual[0].getURL().getPath());assertTrue(actual[0].closed);
        assertThrows(IllegalArgumentException.class,()->c.stock(TOKEN,"other-store",null));
        assertThrows(IOException.class,()->c.stock(TOKEN,"runner","../../orders"));
    }
    @Test public void expiredSessionAndHugeResponsesAreNotDisplayed() throws Exception {
        CentralClient expired=new CentralClient("https://central.example",url->{Connection c=new Connection(url);c.code=401;return c;});
        assertThrows(CentralClient.AccessDenied.class,()->expired.overview(TOKEN));
        CentralClient huge=new CentralClient("https://central.example",url->{Connection c=new Connection(url);c.payload=new byte[1_048_577];return c;});
        assertThrows(IOException.class,()->huge.overview(TOKEN));
    }
}
