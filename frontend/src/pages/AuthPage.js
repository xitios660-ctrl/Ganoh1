import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { motion } from 'framer-motion';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { User, Lock, UserPlus, LogIn, Store, AlertCircle, ArrowLeft } from 'lucide-react';
import { Toaster, toast } from 'sonner';
import { CinematicBackground } from '../components/CinematicBackground';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const LOGO_URL = "/assets/ganoh-logo.png";

export const AuthPage = () => {
  const navigate = useNavigate();
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('login');
  const [accounts, setAccounts] = useState([]);
  const [canCreate, setCanCreate] = useState(true);
  
  // Login form
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  
  // Register form
  const [registerUsername, setRegisterUsername] = useState('');
  const [registerPassword, setRegisterPassword] = useState('');
  const [registerDisplayName, setRegisterDisplayName] = useState('');

  useEffect(() => {
    // Revalidate stored session against backend before auto-redirecting.
    // Prevents being stuck in a broken state when the tenant was deleted
    // or the local storage data is stale.
    const tenantId = localStorage.getItem('tenant_id');
    if (tenantId) {
      axios.get(`${API}/auth/check/${tenantId}`)
        .then(() => navigate('/gestor/dashboard'))
        .catch(() => {
          // Stale/invalid session — clear and stay on /auth
          localStorage.removeItem('tenant_id');
          localStorage.removeItem('tenant_username');
          localStorage.removeItem('tenant_display_name');
          localStorage.removeItem('gestor_auth');
        });
    }

    // Fetch existing accounts
    fetchAccounts();
  }, [navigate]);

  const fetchAccounts = async () => {
    try {
      const response = await axios.get(`${API}/auth/accounts`);
      setAccounts(response.data.accounts || []);
      setCanCreate(response.data.can_create);
    } catch (error) {
      console.error('Error fetching accounts:', error);
    }
  };

  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    
    // Trim whitespace to prevent mobile keyboard issues (auto-space, etc)
    const cleanUsername = (loginUsername || '').trim();
    const cleanPassword = (loginPassword || '').trim();
    
    try {
      const response = await axios.post(`${API}/auth/login`, {
        username: cleanUsername,
        password: cleanPassword
      });
      
      // Save auth info
      localStorage.setItem('tenant_id', response.data.tenant_id);
      localStorage.setItem('tenant_username', response.data.username);
      localStorage.setItem('tenant_display_name', response.data.display_name);
      localStorage.setItem('gestor_auth', btoa(`${cleanUsername}:${cleanPassword}`));
      
      toast.success('Login realizado com sucesso!');
      navigate('/gestor/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Credenciais inválidas');
    } finally {
      setIsLoading(false);
    }
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    
    if (!canCreate) {
      toast.error('Limite máximo de contas atingido (2)');
      return;
    }
    
    setIsLoading(true);
    
    try {
      const response = await axios.post(`${API}/auth/register`, {
        username: registerUsername,
        password: registerPassword,
        display_name: registerDisplayName || registerUsername
      });
      
      toast.success('Conta criada com sucesso! Faça login para continuar.');
      setActiveTab('login');
      setLoginUsername(registerUsername);
      setLoginPassword('');
      fetchAccounts();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao criar conta');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="ganoh-dark-scene min-h-screen bg-[#070707] flex items-center justify-center p-4 relative overflow-hidden">
      <Toaster richColors position="top-center" />

      <CinematicBackground accent="#a8d96b" />

      {/* Back to home */}
      <button
        onClick={() => navigate('/')}
        className="absolute top-6 left-6 z-20 flex items-center gap-2 text-[10px] uppercase tracking-[0.3em] text-white/40 hover:text-[#a8d96b] transition font-display"
        data-testid="auth-back-btn"
      >
        <ArrowLeft className="h-3 w-3" /> Voltar
      </button>

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        className="w-full max-w-md relative z-10"
      >
          <Card className="w-full relative bg-white/[0.04] backdrop-blur-2xl border-white/10 shadow-[0_24px_64px_-12px_rgba(0,0,0,0.7),inset_0_1px_0_rgba(255,255,255,0.06)] text-white">
            {/* corner glow */}
            <div className="absolute -top-12 -right-12 w-44 h-44 rounded-full blur-3xl pointer-events-none"
              style={{ background: 'radial-gradient(circle, rgba(168,217,107,0.3), transparent 70%)' }} />

            <CardHeader className="text-center pb-2 relative">
              <div className="relative inline-block mx-auto mb-3">
                {/* Rotating ring */}
                <div className="absolute inset-0 -m-3 rounded-full border border-[#a8d96b]/15 ganoh-spin-slow" />
                <div className="absolute inset-0 -m-4 rounded-full blur-2xl bg-[#a8d96b]/30" />
                <img src={LOGO_URL} alt="GANOH" className="relative h-16 mx-auto drop-shadow-[0_0_24px_rgba(168,217,107,0.5)]" style={{ filter: 'brightness(1.7) contrast(1.2) saturate(1.1)' }} />
              </div>
              <p className="font-display italic text-[10px] uppercase tracking-[0.45em] text-[#a8d96b]/80 mt-2">Acesso Restrito</p>
              <CardTitle className="font-heading text-3xl font-light text-white mt-1 tracking-tight">
                Painel do <span className="font-display italic text-[#a8d96b] font-medium">Gestor</span>
              </CardTitle>
              <div className="mx-auto mt-3 h-px w-12 bg-gradient-to-r from-transparent via-[#a8d96b]/60 to-transparent" />
              <CardDescription className="text-white/50 text-sm mt-3 font-light">
                Acesse ou crie sua conta para gerenciar
              </CardDescription>
            </CardHeader>
        
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-2 mb-6 bg-white/[0.04] border border-white/10">
              <TabsTrigger value="login" className="flex items-center gap-2 data-[state=active]:bg-[#a8d96b]/15 data-[state=active]:text-[#a8d96b] text-white/60">
                <LogIn className="h-4 w-4" /> Entrar
              </TabsTrigger>
              <TabsTrigger value="register" className="flex items-center gap-2 data-[state=active]:bg-[#a8d96b]/15 data-[state=active]:text-[#a8d96b] text-white/60" disabled={!canCreate}>
                <UserPlus className="h-4 w-4" /> Criar Conta
              </TabsTrigger>
            </TabsList>
            
            {/* Login Tab */}
            <TabsContent value="login">
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="login-username" className="flex items-center gap-2 text-white/70 text-xs uppercase tracking-wider">
                    <User className="h-3.5 w-3.5 text-[#a8d96b]/60" /> Usuário
                  </Label>
                  <Input
                    id="login-username"
                    type="text"
                    placeholder="Digite seu usuário"
                    value={loginUsername}
                    onChange={(e) => setLoginUsername(e.target.value)}
                    required
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck="false"
                    className="bg-white/[0.04] border-white/10 text-white placeholder:text-white/30 focus:border-[#a8d96b]/50 focus-visible:ring-[#a8d96b]/20"
                    data-testid="login-username"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="login-password" className="flex items-center gap-2 text-white/70 text-xs uppercase tracking-wider">
                    <Lock className="h-3.5 w-3.5 text-[#a8d96b]/60" /> Senha
                  </Label>
                  <Input
                    id="login-password"
                    type="password"
                    placeholder="Digite sua senha"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                    autoCapitalize="none"
                    autoCorrect="off"
                    spellCheck="false"
                    className="bg-white/[0.04] border-white/10 text-white placeholder:text-white/30 focus:border-[#a8d96b]/50 focus-visible:ring-[#a8d96b]/20"
                    data-testid="login-password"
                  />
                </div>
                
                <Button 
                  type="submit" 
                  className="w-full bg-[#a8d96b] hover:bg-[#94c558] text-[#0a0a0a] font-medium tracking-wide transition-all hover:scale-[1.01] active:scale-[0.99]"
                  disabled={isLoading}
                  data-testid="login-submit"
                >
                  {isLoading ? 'Entrando...' : 'Entrar →'}
                </Button>
              </form>
              
              {/* Account listing removed for security - prevents user enumeration */}
            </TabsContent>
            
            {/* Register Tab */}
            <TabsContent value="register">
              {!canCreate ? (
                <div className="text-center py-8">
                  <AlertCircle className="h-12 w-12 mx-auto text-amber-400 mb-4" />
                  <p className="text-white/70">
                    Limite máximo de 2 contas atingido.
                  </p>
                  <p className="text-sm text-white/40 mt-2">
                    Entre com uma conta existente.
                  </p>
                </div>
              ) : (
                <form onSubmit={handleRegister} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="register-display" className="flex items-center gap-2 text-white/70 text-xs uppercase tracking-wider">
                      <Store className="h-3.5 w-3.5 text-[#a8d96b]/60" /> Nome da Loja
                    </Label>
                    <Input
                      id="register-display"
                      type="text"
                      placeholder="Ex: Minha Loja"
                      value={registerDisplayName}
                      onChange={(e) => setRegisterDisplayName(e.target.value)}
                      className="bg-white/[0.04] border-white/10 text-white placeholder:text-white/30 focus:border-[#a8d96b]/50 focus-visible:ring-[#a8d96b]/20"
                      data-testid="register-display"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="register-username" className="flex items-center gap-2 text-white/70 text-xs uppercase tracking-wider">
                      <User className="h-3.5 w-3.5 text-[#a8d96b]/60" /> Usuário
                    </Label>
                    <Input
                      id="register-username"
                      type="text"
                      placeholder="Escolha um nome de usuário"
                      value={registerUsername}
                      onChange={(e) => setRegisterUsername(e.target.value)}
                      required
                      autoCapitalize="none"
                      autoCorrect="off"
                      spellCheck="false"
                      className="bg-white/[0.04] border-white/10 text-white placeholder:text-white/30 focus:border-[#a8d96b]/50 focus-visible:ring-[#a8d96b]/20"
                      data-testid="register-username"
                    />
                  </div>
                  
                  <div className="space-y-2">
                    <Label htmlFor="register-password" className="flex items-center gap-2 text-white/70 text-xs uppercase tracking-wider">
                      <Lock className="h-3.5 w-3.5 text-[#a8d96b]/60" /> Senha
                    </Label>
                    <Input
                      id="register-password"
                      type="password"
                      placeholder="Escolha uma senha forte"
                      value={registerPassword}
                      onChange={(e) => setRegisterPassword(e.target.value)}
                      required
                      minLength={4}
                      className="bg-white/[0.04] border-white/10 text-white placeholder:text-white/30 focus:border-[#a8d96b]/50 focus-visible:ring-[#a8d96b]/20"
                      data-testid="register-password"
                    />
                  </div>
                  
                  <Button 
                    type="submit" 
                    className="w-full bg-[#a8d96b] hover:bg-[#94c558] text-[#0a0a0a] font-medium tracking-wide transition-all hover:scale-[1.01] active:scale-[0.99]"
                    disabled={isLoading}
                    data-testid="register-submit"
                  >
                    {isLoading ? 'Criando...' : 'Criar Conta →'}
                  </Button>
                  
                  <p className="text-[10px] uppercase tracking-widest text-center text-white/40 mt-4">
                    {accounts.length}/2 contas criadas
                  </p>
                </form>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
      </motion.div>
    </div>
  );
};

export default AuthPage;
