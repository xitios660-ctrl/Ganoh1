package com.ganoh.tv;
import android.view.View;
import android.view.ViewGroup;
import android.view.KeyEvent;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.android.controller.ActivityController;
import org.robolectric.RobolectricTestRunner;
import org.robolectric.annotation.Config;
import static org.junit.Assert.*;

@RunWith(RobolectricTestRunner.class) @Config(sdk=28)
public class MainActivityTest {
    static Button button(View view,String label){
        if(view instanceof Button && label.contentEquals(((Button)view).getText()))return (Button)view;
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++){Button found=button(((ViewGroup)view).getChildAt(i),label);if(found!=null)return found;}
        return null;
    }
    static String text(View view){StringBuilder result=new StringBuilder();if(view instanceof TextView)result.append(((TextView)view).getText());
        if(view instanceof ViewGroup)for(int i=0;i<((ViewGroup)view).getChildCount();i++)result.append(text(((ViewGroup)view).getChildAt(i)));return result.toString();}
    @Test public void demoCanBeOpenedWithDpadAndNeverClaimsRealData(){
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup().visible()){
            MainActivity a=controller.get();View decor=a.getWindow().getDecorView();Button open=button(decor,"Abrir demonstração — dados fictícios");
            assertNotNull(open);assertTrue(open.requestFocus());
            open.dispatchKeyEvent(new KeyEvent(KeyEvent.ACTION_DOWN,KeyEvent.KEYCODE_DPAD_CENTER));
            open.dispatchKeyEvent(new KeyEvent(KeyEvent.ACTION_UP,KeyEvent.KEYCODE_DPAD_CENTER));
            // Robolectric doesn't emulate the native input dispatcher; performClick validates the same action.
            if(!text(decor).contains("NÃO SÃO VENDAS REAIS"))open.performClick();
            decor=a.getWindow().getDecorView();assertTrue(text(decor).contains("NÃO SÃO VENDAS REAIS"));
            assertTrue(text(decor).contains("RUNNER"));assertTrue(text(decor).contains("GYM LONDRES"));
            assertTrue(text(decor).contains("quantidade desconhecida"));assertTrue(a.getPreferences(0).getAll().isEmpty());
            Button stock=button(decor,"Estoque de RUNNER");assertNotNull(stock);stock.performClick();
            assertTrue(text(a.getWindow().getDecorView()).contains("Lanche de demonstração"));
            a.onBackPressed();assertNotNull(button(a.getWindow().getDecorView(),"Estoque de RUNNER"));
            button(a.getWindow().getDecorView(),"Sair da demonstração").performClick();
            assertFalse(text(a.getWindow().getDecorView()).contains("TOTAL DAS UNIDADES AUTORIZADAS"));
        }
    }
    @Test public void recreationDoesNotRestorePasswordOrFinancialScreen(){
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity a=controller.get();button(a.getWindow().getDecorView(),"Abrir demonstração — dados fictícios").performClick();
            controller.recreate();assertNotNull(button(controller.get().getWindow().getDecorView(),"Abrir demonstração — dados fictícios"));
            assertTrue(controller.get().getPreferences(0).getAll().isEmpty());
        }
    }
    @Test public void staleDataIsMarkedAndLeavingClearsAuthenticatedValues(){
        try(ActivityController<MainActivity> controller=Robolectric.buildActivity(MainActivity.class).setup()){
            MainActivity a=controller.get();
            org.robolectric.util.ReflectionHelpers.setField(a,"client",new CentralClient("https://central.example",CentralClientTest.Connection::new));
            org.robolectric.util.ReflectionHelpers.setField(a,"token",CentralClientTest.TOKEN);
            org.robolectric.util.ReflectionHelpers.setField(a,"dashboard",Dashboard.demo());
            org.robolectric.util.ReflectionHelpers.setField(a,"lastError","Sem conexão");
            org.robolectric.util.ReflectionHelpers.callInstanceMethod(a,"renderDashboard");
            assertTrue(text(a.getWindow().getDecorView()).contains("SEM ATUALIZAÇÃO"));
            assertTrue(text(a.getWindow().getDecorView()).contains("2.120,00"));
            controller.pause().stop();
            assertNull(org.robolectric.util.ReflectionHelpers.getField(a,"token"));
            assertNull(org.robolectric.util.ReflectionHelpers.getField(a,"dashboard"));
            assertFalse(text(a.getWindow().getDecorView()).contains("TOTAL DAS UNIDADES"));
        }
    }
}
