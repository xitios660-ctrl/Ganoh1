import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UserPlus, CalendarClock, Plus, Minus, History, Trash2,
  TrendingUp, TrendingDown, Wallet, Receipt, X, Search,
  ArrowUpRight, ArrowDownRight, CreditCard, BadgeDollarSign,
} from 'lucide-react';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { Button } from '../ui/button';

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const formatPrice = (v) => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0);

const EVENT_META = {
  debt_added:     { label: 'Dívida adicionada', icon: ArrowUpRight,   tone: 'rose'   },
  debt_removed:   { label: 'Valor removido',    icon: ArrowDownRight, tone: 'emerald'},
  payment_full:   { label: 'Quitação total',    icon: BadgeDollarSign,tone: 'emerald'},
  payment_partial:{ label: 'Pagamento parcial', icon: CreditCard,     tone: 'cyan'   },
  credit_added:   { label: 'Crédito adicionado',icon: Wallet,         tone: 'violet' },
  credit_used:    { label: 'Crédito utilizado', icon: Wallet,         tone: 'gold'   },
};

const fmtDate = (iso) => {
  try {
    const d = new Date(iso);
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch { return iso || ''; }
};

const ActionDialog = ({ open, onClose, mode, customer, onDone }) => {
  const [amount, setAmount] = useState('');
  const [password, setPassword] = useState('');
  const [notes, setNotes] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) { setAmount(''); setPassword(''); setNotes(''); setPaymentMethod('cash'); }
  }, [open]);

  const isAdd = mode === 'add';
  const title = isAdd ? 'Adicionar valor à dívida' : 'Remover valor da dívida';

  const submit = async (e) => {
    e.preventDefault();
    const val = parseFloat(amount);
    if (!val || val <= 0) { toast.error('Valor inválido'); return; }
    if (!password) { toast.error('Informe a senha'); return; }
    setSubmitting(true);
    try {
      const endpoint = isAdd ? 'add' : 'remove';
      const { data } = await axios.post(
        `${API}/prazo/customers/${customer.id}/debt/${endpoint}`,
        { password, amount: val, notes, payment_method: paymentMethod }
      );
      toast.success(data.message || 'Operação realizada');
      onDone?.();
      onClose();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Falha na operação');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="gx-dialog-content max-w-md" data-testid="prazo-action-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2" style={{ color: 'var(--gx-ink)' }}>
            {isAdd ? <Plus className="h-5 w-5" style={{ color: 'var(--gx-rose)' }} /> : <Minus className="h-5 w-5" style={{ color: 'var(--gx-emerald)' }} />}
            {title}
          </DialogTitle>
        </DialogHeader>
        <div className="text-xs uppercase tracking-[3px]" style={{ color: 'var(--gx-gold)' }}>{customer?.name}</div>

        <form onSubmit={submit} className="space-y-3 mt-2">
          <div>
            <label className="text-xs" style={{ color: 'var(--gx-mute)' }}>Valor (R$)</label>
            <input
              type="number" step="0.01" min="0" value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="gx-input" placeholder="0,00" autoFocus
              data-testid="prazo-action-amount"
            />
          </div>

          {!isAdd && (
            <div>
              <label className="text-xs" style={{ color: 'var(--gx-mute)' }}>Forma de pagamento</label>
              <select
                value={paymentMethod}
                onChange={(e) => setPaymentMethod(e.target.value)}
                className="gx-input"
                data-testid="prazo-action-method"
              >
                <option value="cash">Dinheiro</option>
                <option value="pix">PIX</option>
                <option value="debit">Débito</option>
                <option value="credit">Crédito</option>
              </select>
            </div>
          )}

          <div>
            <label className="text-xs" style={{ color: 'var(--gx-mute)' }}>Observação (opcional)</label>
            <input
              type="text" value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="gx-input" placeholder={isAdd ? 'Ex.: Pedido manual' : 'Ex.: Pagamento em loja'}
              data-testid="prazo-action-notes"
            />
          </div>

          <div>
            <label className="text-xs" style={{ color: 'var(--gx-mute)' }}>Senha</label>
            <input
              type="password" value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="gx-input" placeholder="••••"
              data-testid="prazo-action-password"
            />
          </div>

          {!isAdd && (
            <p className="text-[11px]" style={{ color: 'var(--gx-mute)' }}>
              Se o valor exceder a dívida, o excedente será convertido em crédito do cliente.
            </p>
          )}

          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose} className="gx-btn-ghost flex-1" data-testid="prazo-action-cancel">
              Cancelar
            </button>
            <button
              type="submit" disabled={submitting}
              className={isAdd ? 'gx-btn-rose flex-1' : 'gx-btn-emerald flex-1'}
              data-testid="prazo-action-submit"
            >
              {submitting ? 'Processando…' : isAdd ? 'Adicionar' : 'Remover'}
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};

const HistoryDialog = ({ open, onClose, customer }) => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !customer?.id) return;
    setLoading(true);
    axios.get(`${API}/prazo/customers/${customer.id}/history`)
      .then((res) => setData(res.data))
      .catch(() => toast.error('Erro ao carregar histórico'))
      .finally(() => setLoading(false));
  }, [open, customer?.id]);

  const events = data?.events || [];

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="gx-dialog-content max-w-2xl max-h-[85vh] overflow-hidden p-0" data-testid="prazo-history-dialog">
        <div className="px-6 pt-5 pb-3 border-b" style={{ borderColor: 'var(--gx-line)' }}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2" style={{ color: 'var(--gx-ink)' }}>
              <History className="h-5 w-5" style={{ color: 'var(--gx-gold)' }} />
              Histórico — {customer?.name}
            </DialogTitle>
          </DialogHeader>
          {data?.customer && (
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div className="gx-row" style={{ padding: '8px 12px' }}>
                <span style={{ color: 'var(--gx-mute)' }}>Dívida atual</span>
                <span className="font-bold" style={{ color: 'var(--gx-rose)' }}>{formatPrice(data.customer.current_debt)}</span>
              </div>
              <div className="gx-row" style={{ padding: '8px 12px' }}>
                <span style={{ color: 'var(--gx-mute)' }}>Crédito</span>
                <span className="font-bold" style={{ color: 'var(--gx-emerald)' }}>{formatPrice(data.customer.credit)}</span>
              </div>
              <div className="gx-row" style={{ padding: '8px 12px' }}>
                <span style={{ color: 'var(--gx-mute)' }}>Eventos</span>
                <span className="font-bold" style={{ color: 'var(--gx-gold)' }}>{data.total_count}</span>
              </div>
            </div>
          )}
        </div>

        <div className="px-6 py-4 overflow-y-auto gx-scroll" style={{ maxHeight: '60vh' }}>
          {loading ? (
            <div className="text-center py-10" style={{ color: 'var(--gx-mute)' }}>Carregando…</div>
          ) : events.length === 0 ? (
            <div className="text-center py-12" style={{ color: 'var(--gx-mute)' }}>
              <Receipt className="h-10 w-10 mx-auto opacity-40 mb-3" />
              Sem eventos registrados.
            </div>
          ) : (
            <div className="gx-timeline">
              <AnimatePresence>
                {events.map((ev, i) => {
                  const meta = EVENT_META[ev.event_type] || { label: ev.event_type, icon: Receipt, tone: 'gold' };
                  const Icon = meta.icon;
                  return (
                    <motion.div
                      key={ev.id || i}
                      initial={{ opacity: 0, x: -10 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.04, duration: 0.35, ease: [0.2, 0.8, 0.2, 1] }}
                      className="gx-tl-item"
                      data-testid={`prazo-history-event-${i}`}
                    >
                      <span className={`gx-tl-dot ${meta.tone}`} />
                      <div className="gx-tl-card">
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div className="flex items-center gap-2">
                            <Icon className="h-4 w-4" style={{ color: `var(--gx-${meta.tone})` }} />
                            <span className="text-sm font-semibold" style={{ color: 'var(--gx-ink)' }}>{meta.label}</span>
                            <span className={`gx-pill ${meta.tone}`}>{formatPrice(ev.amount)}</span>
                          </div>
                          <span className="text-[11px]" style={{ color: 'var(--gx-mute)' }}>{fmtDate(ev.created_at)}</span>
                        </div>
                        <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]" style={{ color: 'var(--gx-mute)' }}>
                          {ev.previous_debt !== undefined && (
                            <div>Dívida: <span style={{ color: 'var(--gx-ink)' }}>{formatPrice(ev.previous_debt)} → {formatPrice(ev.new_debt)}</span></div>
                          )}
                          {ev.credit_generated > 0 && (
                            <div>+ Crédito: <span style={{ color: 'var(--gx-emerald)' }}>{formatPrice(ev.credit_generated)}</span></div>
                          )}
                          {ev.new_credit !== undefined && ev.new_credit !== ev.previous_credit && (
                            <div>Saldo: <span style={{ color: 'var(--gx-ink)' }}>{formatPrice(ev.previous_credit)} → {formatPrice(ev.new_credit)}</span></div>
                          )}
                          {ev.payment_method && <div>Método: <span style={{ color: 'var(--gx-ink)' }}>{ev.payment_method}</span></div>}
                          {ev.notes && <div className="col-span-2 md:col-span-4 italic">“{ev.notes}”</div>}
                        </div>
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          )}
        </div>

        <div className="px-6 py-3 border-t flex justify-end" style={{ borderColor: 'var(--gx-line)' }}>
          <button onClick={onClose} className="gx-btn-ghost" data-testid="prazo-history-close">
            <X className="h-4 w-4" /> Fechar
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const PrazoTab = ({ prazoCustomers, prazoDebts, onOpenNewCustomer, onDeleteCustomer, onRefresh }) => {
  const [query, setQuery] = useState('');
  const [storeFilter, setStoreFilter] = useState('all'); // 'all' | 'runner' | 'gym-londres'
  const [action, setAction] = useState({ open: false, mode: 'add', customer: null });
  const [history, setHistory] = useState({ open: false, customer: null });

  // Filter customers by selected store
  const customersByStore = useMemo(() => {
    const list = prazoCustomers || [];
    if (storeFilter === 'all') return list;
    return list.filter((c) => (c.store || '').toLowerCase() === storeFilter);
  }, [prazoCustomers, storeFilter]);

  // Filter debts by selected store (debts have a `store` field on the order)
  const debtsByStore = useMemo(() => {
    const all = prazoDebts?.debts || [];
    if (storeFilter === 'all') return all;
    return all.filter((d) => {
      // Match debt to a customer in the selected store
      const matchingCustomer = (prazoCustomers || []).find(
        (c) => (c.name || '').toLowerCase() === (d.name || '').toLowerCase()
              && (c.store || '').toLowerCase() === storeFilter
      );
      return !!matchingCustomer;
    });
  }, [prazoDebts, prazoCustomers, storeFilter]);

  const totalPrazoFiltered = useMemo(() => {
    return debtsByStore.reduce((s, d) => s + (d.total || 0), 0);
  }, [debtsByStore]);

  const debtMap = useMemo(() => {
    const m = {};
    debtsByStore.forEach((d) => { m[(d.name || '').toLowerCase()] = d; });
    return m;
  }, [debtsByStore]);

  const filtered = useMemo(() => {
    const norm = (s) => (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    const q = norm(query.trim());
    const list = customersByStore;
    if (!q) return list;
    return list.filter((c) => norm(c.name).includes(q) || (c.phone || '').includes(q));
  }, [customersByStore, query]);

  const customersWithDebt = useMemo(() => {
    // Count of distinct customers that have any pending debt under the selected store
    const setNames = new Set();
    debtsByStore.forEach((d) => {
      if ((d.total || 0) > 0) setNames.add((d.name || '').toLowerCase());
    });
    return setNames.size;
  }, [debtsByStore]);

  const topDebt = debtsByStore[0];

  return (
    <div className="space-y-6">
      {/* Store filter - clarifies that data IS consolidated across stores unless filtered */}
      <div className="flex items-center gap-2 flex-wrap" data-testid="prazo-store-filter">
        <span className="text-sm font-medium" style={{ color: 'var(--gx-ink)' }}>
          Loja:
        </span>
        {[
          { id: 'all', label: 'Todas (consolidado)' },
          { id: 'runner', label: '🏃 Runner' },
          { id: 'gym-londres', label: '🏋️ GYM Londres' }
        ].map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setStoreFilter(opt.id)}
            data-testid={`prazo-store-${opt.id}`}
            className={`gx-seg-btn ${storeFilter === opt.id ? 'active' : ''}`}
          >
            {opt.label}
          </button>
        ))}
        <span className="text-xs ml-auto" style={{ color: 'var(--gx-muted)' }}>
          {storeFilter === 'all'
            ? 'Mostrando dados de todas as unidades'
            : `Mostrando apenas: ${storeFilter === 'runner' ? 'Runner' : 'GYM Londres'}`}
        </span>
      </div>

      {/* KPIs */}
      <div className="gx-kpi-grid">
        <motion.div className="gx-kpi gx-enter" data-i="1" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}>
          <div className="gx-kpi-label">
            <span className="gx-kpi-icon"><CalendarClock className="h-4 w-4" /></span> Total a receber
          </div>
          <div className="gx-kpi-value gx-counter" data-testid="prazo-kpi-total">{formatPrice(totalPrazoFiltered)}</div>
          <div className="gx-kpi-foot">{customersWithDebt} cliente(s) com débito</div>
        </motion.div>
        <motion.div className="gx-kpi gx-enter" data-i="2" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.05 }}>
          <div className="gx-kpi-label">
            <span className="gx-kpi-icon cyan"><UserPlus className="h-4 w-4" /></span> Clientes cadastrados
          </div>
          <div className="gx-kpi-value gx-counter">{customersByStore.length}</div>
          <div className="gx-kpi-foot">Cadastro ativo</div>
        </motion.div>
        <motion.div className="gx-kpi gx-enter" data-i="3" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.1 }}>
          <div className="gx-kpi-label">
            <span className="gx-kpi-icon emerald"><Wallet className="h-4 w-4" /></span> Crédito total
          </div>
          <div className="gx-kpi-value gx-counter">
            {formatPrice(customersByStore.reduce((s, c) => s + (c.credit || 0), 0))}
          </div>
          <div className="gx-kpi-foot">Saldo a favor dos clientes</div>
        </motion.div>
        <motion.div className="gx-kpi gx-enter" data-i="4" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.15 }}>
          <div className="gx-kpi-label">
            <span className="gx-kpi-icon rose"><TrendingDown className="h-4 w-4" /></span> Maior dívida
          </div>
          <div className="gx-kpi-value gx-counter">
            {formatPrice(topDebt?.total || 0)}
          </div>
          <div className="gx-kpi-foot">{topDebt?.name || '—'}</div>
        </motion.div>
      </div>

      {/* Customers cinematic card */}
      <motion.div
        className="gx-card"
        initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, delay: 0.18 }}
      >
        <div className="gx-card-head">
          <div className="gx-card-title">
            <UserPlus className="h-5 w-5" style={{ color: 'var(--gx-gold)' }} />
            Clientes Prazo
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="h-3.5 w-3.5 absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--gx-mute)' }} />
              <input
                type="text" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Buscar cliente…"
                className="gx-input"
                style={{ paddingLeft: 32, width: 240, paddingTop: 8, paddingBottom: 8 }}
                data-testid="prazo-search"
              />
            </div>
            <button className="gx-btn-gold" onClick={onOpenNewCustomer} data-testid="prazo-new-customer">
              <Plus className="h-4 w-4" /> Novo Cliente
            </button>
          </div>
        </div>

        <div className="gx-card-body">
          {filtered.length === 0 ? (
            <div className="text-center py-10" style={{ color: 'var(--gx-mute)' }}>
              <UserPlus className="h-10 w-10 mx-auto opacity-30 mb-2" />
              <p>{query ? 'Nenhum cliente encontrado.' : 'Nenhum cliente cadastrado.'}</p>
            </div>
          ) : (
            <div className="space-y-2.5">
              {filtered.map((c, idx) => {
                const d = debtMap[(c.name || '').toLowerCase()];
                const debtTotal = d?.total || 0;
                const credit = c.credit || 0;
                return (
                  <motion.div
                    key={c.id}
                    className="gx-row"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.04, duration: 0.35 }}
                    data-testid={`prazo-customer-row-${c.id}`}
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <div
                        className="h-10 w-10 rounded-xl grid place-items-center font-bold"
                        style={{
                          background: 'linear-gradient(135deg, rgba(245,198,108,.2), rgba(245,198,108,.05))',
                          border: '1px solid rgba(245,198,108,.3)',
                          color: 'var(--gx-gold)',
                          fontFamily: 'Playfair Display, serif',
                        }}
                      >
                        {(c.name || '?').charAt(0).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <div className="font-semibold truncate" style={{ color: 'var(--gx-ink)' }}>{c.name}</div>
                        <div className="text-[11px] flex items-center gap-2 flex-wrap" style={{ color: 'var(--gx-mute)' }}>
                          {c.phone && <span>{c.phone}</span>}
                          {c.store && <span>• {c.store}</span>}
                          {c.notes && <span className="italic">• {c.notes}</span>}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 flex-wrap justify-end">
                      <span className={`gx-pill ${debtTotal > 0 ? 'rose' : 'emerald'}`}>
                        Dívida {formatPrice(debtTotal)}
                      </span>
                      {credit > 0 && (
                        <span className="gx-pill violet">Crédito {formatPrice(credit)}</span>
                      )}
                      <button
                        className="gx-btn-rose"
                        onClick={() => setAction({ open: true, mode: 'add', customer: c })}
                        data-testid={`prazo-add-${c.id}`}
                        title="Adicionar valor"
                      >
                        <Plus className="h-3.5 w-3.5" /> Adicionar
                      </button>
                      <button
                        className="gx-btn-emerald"
                        onClick={() => setAction({ open: true, mode: 'remove', customer: c })}
                        data-testid={`prazo-remove-${c.id}`}
                        title="Remover valor"
                      >
                        <Minus className="h-3.5 w-3.5" /> Remover
                      </button>
                      <button
                        className="gx-btn-ghost"
                        onClick={() => setHistory({ open: true, customer: c })}
                        data-testid={`prazo-history-${c.id}`}
                        title="Histórico"
                      >
                        <History className="h-3.5 w-3.5" /> Histórico
                      </button>
                      <button
                        className="gx-icon-btn"
                        onClick={() => onDeleteCustomer(c.id)}
                        style={{ color: 'var(--gx-rose)' }}
                        data-testid={`prazo-delete-${c.id}`}
                        title="Remover cliente"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          )}
        </div>
      </motion.div>

      <ActionDialog
        open={action.open}
        mode={action.mode}
        customer={action.customer}
        onClose={() => setAction({ ...action, open: false })}
        onDone={onRefresh}
      />
      <HistoryDialog
        open={history.open}
        customer={history.customer}
        onClose={() => setHistory({ ...history, open: false })}
      />
    </div>
  );
};

export default PrazoTab;
