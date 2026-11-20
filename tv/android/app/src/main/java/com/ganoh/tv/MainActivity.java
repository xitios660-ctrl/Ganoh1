package com.ganoh.tv;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Native, remote-friendly, read-only companion. No WebView or production fallback. */
public final class MainActivity extends Activity {
    static final int BG=0xff10151d, CARD=0xff1b2635, TEXT=0xfff2f5f9, MUTED=0xffbac7d8, ORANGE=0xffff8a35;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private final List<Button> buttons=new ArrayList<>();
    private LinearLayout root;
    private EditText serverInput,usernameInput,passwordInput;
    private TextView message;
    private CentralClient client;
    private String token;
    private Dashboard dashboard;
    private StockPage stock;
    private boolean demo,loading,destroyed;
    private String lastError="";
    private int epoch;
    private final Runnable poll=new Runnable(){public void run(){
        if (!demo && token!=null && !loading) refresh();
        handler.postDelayed(this,30_000);
    }};
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        showLogin();
    }
    @Override protected void onResume(){super.onResume();handler.removeCallbacks(poll);handler.postDelayed(poll,30_000);}
    @Override protected void onPause(){handler.removeCallbacks(poll);super.onPause();}
    @Override protected void onStop(){
        // TV is shared: leaving the app clears financial content and credentials.
        if (token!=null || loading) logout();
        super.onStop();
    }
    @Override protected void onDestroy(){destroyed=true;epoch++;handler.removeCallbacksAndMessages(null);worker.shutdownNow();super.onDestroy();}
    private int dp(int value){return (int)(value*getResources().getDisplayMetrics().density+.5f);}
    private LinearLayout vertical(){LinearLayout view=new LinearLayout(this);view.setOrientation(LinearLayout.VERTICAL);return view;}
    private void screen(String title){
        buttons.clear();root=vertical();root.setPadding(dp(42),dp(24),dp(42),dp(32));root.setBackgroundColor(BG);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.addView(root);
        setContentView(scroll);text(root,"GANOH TV",32,ORANGE).setTypeface(null,Typeface.BOLD);
        text(root,title,23,TEXT);
    }
    private TextView text(LinearLayout parent,String value,int size,int color){
        TextView view=new TextView(this);view.setText(value);view.setTextSize(size);view.setTextColor(color);
        view.setPadding(0,dp(7),0,dp(7));parent.addView(view);return view;
    }
    private GradientDrawable shape(int color,int stroke){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(8));d.setStroke(dp(3),stroke);return d;}
    private Button button(LinearLayout parent,String label,Runnable action){
        Button view=new Button(this);view.setId(View.generateViewId());view.setText(label);view.setTextSize(19);
        view.setAllCaps(false);view.setMinHeight(dp(56));view.setPadding(dp(20),dp(8),dp(20),dp(8));
        StateListDrawable background=new StateListDrawable();
        background.addState(new int[]{android.R.attr.state_focused},shape(0xff473120,ORANGE));
        background.addState(new int[]{},shape(CARD,0xff51647d));view.setBackground(background);
        view.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{0xff748197,TEXT}));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-2,-2);params.setMargins(0,dp(8),dp(16),dp(8));
        parent.addView(view,params);view.setOnClickListener(v->action.run());buttons.add(view);return view;
    }
    private EditText input(String label,int type){
        text(root,label,18,MUTED);EditText input=new EditText(this);input.setId(View.generateViewId());
        input.setTextSize(20);input.setSingleLine(true);input.setInputType(type);input.setTextColor(TEXT);
        input.setHintTextColor(MUTED);input.setSaveEnabled(false);input.setContentDescription(label);
        input.setMinHeight(dp(52));root.addView(input,new LinearLayout.LayoutParams(dp(640),-2));return input;
    }
    private void showLogin(){
        screen("Acompanhamento das lojas • versão demonstrativa");
        text(root,"O aplicativo Windows e o site atual continuam separados. Nenhuma informação de produção é carregada automaticamente.",18,MUTED);
        button(root,"Abrir demonstração — dados fictícios",()->{
            epoch++;demo=true;token=null;dashboard=Dashboard.demo();stock=null;lastError="";loading=false;renderDashboard();
        });
        serverInput=input("Servidor HTTPS de homologação",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setText(getPreferences(MODE_PRIVATE).getString("origin",""));
        serverInput.setHint("https://central-de-homologacao");
        usernameInput=input("Usuário exclusivo da TV",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_VISIBLE_PASSWORD);
        passwordInput=input("Senha exclusiva da TV",InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        passwordInput.setLongClickable(false);
        if (android.os.Build.VERSION.SDK_INT>=26) passwordInput.setImportantForAutofill(View.IMPORTANT_FOR_AUTOFILL_NO_EXCLUDE_DESCENDANTS);
        button(root,"Entrar na homologação",this::login);
        message=text(root,"Crie o acesso da TV no painel do proprietário da homologação. Não use a senha do proprietário ou de produção. Senha e sessão não são gravadas na TV.",18,MUTED);
        buttons.get(0).requestFocus();
        getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }
    private void busy(boolean value){loading=value;for(Button b:buttons)b.setEnabled(!value);}
    private void login(){
        final String user=usernameInput.getText().toString().trim();final String password=passwordInput.getText().toString();
        try{client=new CentralClient(serverInput.getText().toString());}
        catch(IllegalArgumentException error){message.setText(error.getMessage());return;}
        final CentralClient connection=client;final int request=++epoch;demo=false;busy(true);message.setText(R.string.validating);
        worker.execute(()->{
            try {
                JSONObject result=connection.login(user,password);String session=result.getString("access_token");
                Dashboard data;
                try{data=connection.overview(session);}catch(Exception error){try{connection.logout(session);}catch(Exception ignored){}throw error;}
                handler.post(()->{if(destroyed||request!=epoch){if(!worker.isShutdown())worker.execute(()->{try{connection.logout(session);}catch(Exception ignored){}});return;}token=session;dashboard=data;stock=null;lastError="";loading=false;
                    getPreferences(MODE_PRIVATE).edit().putString("origin",CentralClient.origin(serverInput.getText().toString())).apply();
                    passwordInput.setText("");renderDashboard();});
            } catch(Exception error){handler.post(()->{if(destroyed||request!=epoch)return;passwordInput.setText("");busy(false);message.setText(safeError(error));});}
        });
    }
    private String safeError(Exception error){
        if(error instanceof CentralClient.AccessDenied)return error.getMessage();
        if(error instanceof IllegalArgumentException)return error.getMessage();
        return "Sem atualização segura da central. Verifique servidor, conexão e acesso. Nenhum dado foi alterado.";
    }
    private void refresh(){
        if(loading||demo||token==null)return;
        final int request=epoch;final String session=token;final CentralClient connection=client;loading=true;
        worker.execute(()->{
            try{Dashboard data=connection.overview(session);handler.post(()->{
                if(destroyed||request!=epoch)return;dashboard=data;loading=false;lastError="";
                if(stock!=null && !hasUnit(stock.unit))stock=null;renderDashboard();
            });}catch(Exception error){handler.post(()->{
                if(destroyed||request!=epoch)return;loading=false;
                if(error instanceof CentralClient.AccessDenied){logout();message.setText(safeError(error));}
                else{lastError=safeError(error);renderDashboard();}
            });}
        });
    }
    private boolean hasUnit(String unit){for(JSONObject row:dashboard.units)if(unit.equals(row.optString("unit")))return true;return false;}
    private void renderDashboard(){
        String focusLabel=null;View focused=getCurrentFocus();if(focused instanceof Button)focusLabel=((Button)focused).getText().toString();
        screen(demo?"DEMONSTRAÇÃO • DADOS FICTÍCIOS • NÃO SÃO VENDAS REAIS":"HOMOLOGAÇÃO • SOMENTE DADOS CONFIRMADOS");
        if(demo) text(root,"Exemplo para conhecer o aplicativo. Nenhuma conexão com lojas ou servidor.",21,ORANGE);
        else {
            boolean old=!lastError.isEmpty() || android.os.SystemClock.elapsedRealtime()-dashboard.receivedAt>60_000;
            text(root,old?"SEM ATUALIZAÇÃO — valores anteriores podem estar desatualizados":"Central consultada • atualização automática a cada 30 segundos",20,old?ORANGE:MUTED);
            text(root,"Referência da central (UTC): "+dashboard.generatedAt,17,MUTED);
            if(!lastError.isEmpty())text(root,lastError,18,ORANGE);
        }
        text(root,"Valores acumulados do livro de homologação, sem filtro diário.",17,MUTED);
        text(root,"Operações ainda offline nos computadores: quantidade desconhecida pela central.",18,MUTED);
        LinearLayout toolbar=new LinearLayout(this);toolbar.setOrientation(LinearLayout.HORIZONTAL);root.addView(toolbar);
        if(!demo)button(toolbar,"Atualizar resumo",this::refresh);
        if(stock!=null)button(toolbar,"Visão geral",()->{stock=null;renderDashboard();});
        if(stock!=null && !demo)button(toolbar,"Atualizar estoque",()->loadStock(new StockPage(stock.unit)));
        button(toolbar,demo?"Sair da demonstração":"Sair e limpar a sessão",this::logout);
        if(stock==null){
            metricCard("TOTAL DAS UNIDADES AUTORIZADAS",dashboard.total);
            for(JSONObject row:dashboard.units){
                String unit=row.optString("unit");LinearLayout card=metricCard(Dashboard.unitName(unit),row);
                text(card,row.optBoolean("stale")?"SEM CONTATO RECENTE — dados podem estar desatualizados":"Contato recente com a loja",19,row.optBoolean("stale")?ORANGE:MUTED);
                text(card,"Última operação confirmada (UTC): "+(row.isNull("last_sync_at")?"Nenhuma":row.optString("last_sync_at")),17,MUTED);
                text(card,"Conflitos: "+row.optInt("conflicts")+" • Caixas para revisão: "+row.optInt("cash_reviews"),18,MUTED);
                button(card,"Estoque de "+Dashboard.unitName(unit),()->openStock(unit));
            }
        }else{
            text(root,"ESTOQUE CONFIRMADO — "+Dashboard.unitName(stock.unit),26,TEXT);
            text(root,"Snapshot (UTC): "+stock.createdAt+" • Não inclui operações ainda offline.",17,MUTED);
            if(stock.lines.isEmpty())text(root,"Nenhum produto nesta unidade.",21,MUTED);
            for(String line:stock.lines)text(root,line,22,TEXT);
            if(!stock.done)button(root,"Carregar mais produtos",()->loadStock(stock));
        }
        Button target=null;for(Button b:buttons)if(b.getText().toString().equals(focusLabel))target=b;
        if(target==null && !buttons.isEmpty())target=buttons.get(0);if(target!=null)target.requestFocus();
        if(!demo)getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
    }
    private LinearLayout metricCard(String title,JSONObject values){
        LinearLayout card=vertical();card.setPadding(dp(22),dp(12),dp(22),dp(16));card.setBackground(shape(CARD,CARD));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.setMargins(0,dp(12),0,dp(6));root.addView(card,params);
        text(card,title,24,ORANGE);
        text(card,"Vendas: "+Dashboard.money(values.optLong("revenue_cents"))+"    Despesas: "+Dashboard.money(values.optLong("expense_cents")),25,TEXT);
        text(card,"Caixa: "+Dashboard.money(values.optLong("cash_cents"))+"    A prazo: "+Dashboard.money(values.optLong("receivable_cents")),25,TEXT);
        long variance=values.optLong("cash_variance_cents");
        text(card,"Diferenças de caixa: "+Dashboard.money(variance)+"    Resultado: "+Dashboard.money(values.optLong("revenue_cents")-values.optLong("expense_cents")-variance),21,MUTED);
        return card;
    }
    private void openStock(String unit){
        if(!hasUnit(unit))return;
        StockPage page=new StockPage(unit);
        if(demo){
            page.createdAt="Exemplo fictício";page.done=true;page.lines.add("Lanche de demonstração  •  18 un.");page.lines.add("Bebida de demonstração  •  32 un.");stock=page;renderDashboard();
        }else loadStock(page);
    }
    private void loadStock(StockPage page){
        if(loading||token==null||!hasUnit(page.unit))return;
        final int request=epoch;final String session=token;final CentralClient connection=client;loading=true;
        worker.execute(()->{
            try{JSONObject body=connection.stock(session,page.unit,page.nextCursor);
                handler.post(()->{if(destroyed||request!=epoch)return;loading=false;
                    try{page.append(body);stock=page;lastError="";renderDashboard();}
                    catch(Exception error){lastError="Estoque incompatível. Página anterior preservada.";renderDashboard();}
                });
            }catch(Exception error){handler.post(()->{if(destroyed||request!=epoch)return;loading=false;
                if(error instanceof CentralClient.AccessDenied){logout();message.setText(safeError(error));}
                else{lastError=safeError(error);renderDashboard();}
            });}
        });
    }
    private void logout(){
        final String session=token;final CentralClient connection=client;
        epoch++;token=null;dashboard=null;stock=null;demo=false;loading=false;lastError="";showLogin();
        if(session!=null && connection!=null && !worker.isShutdown())worker.execute(()->{try{connection.logout(session);}catch(Exception ignored){/* expires centrally; never retain local bearer */}});
    }
    @Override public void onBackPressed(){
        if(stock!=null){stock=null;renderDashboard();return;}
        if(dashboard!=null){new AlertDialog.Builder(this).setTitle("Sair do GANOH TV?")
                .setMessage("A sessão e os valores serão removidos da tela.").setNegativeButton("Continuar acompanhando",(d,w)->{})
                .setPositiveButton("Sair",(d,w)->logout()).show();return;}
        super.onBackPressed();
    }
}
