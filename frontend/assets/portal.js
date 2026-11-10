/*
 * Portal B2B · Logística — código comum às páginas.
 *
 * - Sessão: guarda o token JWT no navegador. No ambiente de desenvolvimento o
 *   token vem do "Usuários falso"; no portal real, do usuarios-service.
 * - api(): chama o gateway; erros chegam no padrão RFC 7807 e são mostrados
 *   com o título, o detalhe e o correlationId (guia do kit, seção 9.3).
 * - Topo: relógio do módulo (o admin acelera), sino de notificações e usuário.
 */
const Portal = (() => {
  const ICONES = {
    folha: '<path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10Z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/>',
    caminhao: '<path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.62l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/>',
    caixa: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
    calendario: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    predio: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    relogio: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    sino: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    usuario: '<circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 0 0-16 0"/>',
    alfinete: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>',
    arquivo: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4M10 9H8M16 13H8M16 17H8"/>',
    alerta: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
    seta: '<path d="m12 19-7-7 7-7M19 12H5"/>',
    lista: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
    pausa: '<circle cx="12" cy="12" r="10"/><path d="M10 15V9M14 15V9"/>',
    balanca: '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1ZM2 16l3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10M12 3v18M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
    sair: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
  };
  const icone = (nome, classe = 'icone') =>
    `<svg class="${classe}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONES[nome] || ''}</svg>`;

  const escapar = (valor) => String(valor ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ------------------------------------------------------------------ sessão
  const CHAVE = 'portal-b2b.sessao';
  function sessao() {
    try { return JSON.parse(localStorage.getItem(CHAVE)); } catch { return null; }
  }
  function salvarSessao(s) {
    try { localStorage.setItem(CHAVE, JSON.stringify(s)); } catch { /* navegador sem armazenamento */ }
  }
  function sair() {
    try { localStorage.removeItem(CHAVE); } catch { /* idem */ }
    location.reload();
  }

  // ------------------------------------------------------------------ API
  class ErroApi extends Error {
    constructor(problema) {
      super(problema.detail || problema.title || 'Erro');
      this.problema = problema;
      this.status = problema.status;
    }
  }

  async function api(caminho, { metodo = 'GET', corpo, cabecalhos = {} } = {}) {
    const headers = { ...cabecalhos };
    const s = sessao();
    if (s && s.token) headers.Authorization = `Bearer ${s.token}`;
    let body;
    if (corpo !== undefined) { headers['Content-Type'] = 'application/json'; body = JSON.stringify(corpo); }
    let resposta;
    try {
      resposta = await fetch(caminho, { method: metodo, headers, body });
    } catch {
      throw new ErroApi({ title: 'Sem conexão', detail: 'Não foi possível falar com o portal. O ambiente está no ar?', status: 0 });
    }
    const tipo = resposta.headers.get('content-type') || '';
    const dados = tipo.includes('json') ? await resposta.json() : await resposta.text();
    if (!resposta.ok) {
      const problema = typeof dados === 'object' ? dados : { title: 'Erro', detail: String(dados).slice(0, 200) };
      if (resposta.status === 401) { try { localStorage.removeItem(CHAVE); } catch { /* idem */ } mostrarLogin(); }
      throw new ErroApi({ ...problema, status: resposta.status });
    }
    return dados;
  }

  function erroHtml(erro) {
    const p = erro.problema || { title: 'Erro', detail: erro.message };
    return `<div class="aviso erro" role="alert">${icone('alerta')}<div><strong>${escapar(p.title)}</strong> — ${escapar(p.detail)}
      ${p.correlationId ? `<small>Código para o suporte (correlationId): <code>${escapar(p.correlationId)}</code></small>` : ''}</div></div>`;
  }

  // ------------------------------------------------------------------ formatação (horário de Brasília)
  const fuso = 'America/Sao_Paulo';
  const fmtDiaMes = new Intl.DateTimeFormat('pt-BR', { timeZone: fuso, day: '2-digit', month: 'short' });
  const fmtHora = new Intl.DateTimeFormat('pt-BR', { timeZone: fuso, hour: '2-digit', minute: '2-digit' });
  const fmtCompleta = new Intl.DateTimeFormat('pt-BR', { timeZone: fuso, day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
  const fmtData = new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC', day: '2-digit', month: '2-digit', year: 'numeric' });

  const diaMes = (iso) => fmtDiaMes.format(new Date(iso)).replace('.', '').replace(' de ', ' ');
  const formato = {
    curta: (iso) => (iso ? `${diaMes(iso)}, ${fmtHora.format(new Date(iso))}` : '—'),
    diaMes: (iso) => (iso ? diaMes(iso) : '—'),
    hora: (iso) => (iso ? fmtHora.format(new Date(iso)) : ''),
    completa: (iso) => (iso ? fmtCompleta.format(new Date(iso)).replace(',', '') : '—'),
    data: (isoData) => (isoData ? fmtData.format(new Date(`${isoData}T00:00:00Z`)) : '—'),
    moeda: (v) => (v == null ? '—' : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })),
    peso: (kg) => {
      if (kg == null) return '—';
      const t = Number(kg) / 1000;
      return `${t.toLocaleString('pt-BR', { maximumFractionDigits: 1 })} toneladas (${Number(kg).toLocaleString('pt-BR')} kg)`;
    },
    toneladas: (kg) => `${(Number(kg) / 1000).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} t`,
    porcentagem: (p) => `${Math.round(Number(p || 0) * 100)}%`,
    precoTkm: (v) => (v == null ? '—' : `R$ ${Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 3, maximumFractionDigits: 3 })}/t·km`),
    relativo(isoAlvo, isoAgora) {
      if (!isoAlvo || !isoAgora) return '';
      const minutos = Math.round((new Date(isoAlvo) - new Date(isoAgora)) / 60000);
      const abs = Math.abs(minutos);
      const texto = abs < 60 ? `${abs} min` : abs < 48 * 60 ? `${Math.round(abs / 60)} h` : `${Math.round(abs / 1440)} dias`;
      return minutos >= 0 ? `Em ${texto}` : `Há ${texto}`;
    },
    tipoCarga: (t) => ({ GRANEL: 'Granel', REFRIGERADO: 'Refrigerada', CARGA_SECA: 'Carga seca', PERIGOSO: 'Perigosa' }[t] || t),
    veiculo: (t) => (t ? t.toLowerCase().replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase()) : '—'),
  };

  const STATUS_ENTREGA = {
    AGUARDANDO_ALOCACAO: { texto: 'Escalando motorista', cor: 'azul' },
    AGUARDANDO_COLETA: { texto: 'Aguardando coleta', cor: 'ambar' },
    EM_TRANSITO: { texto: 'Em transporte', cor: 'verde' },
    ENTREGUE: { texto: 'Entregue', cor: 'cinza' },
    RECUSADA: { texto: 'Recusada', cor: 'vermelho' },
    CANCELADA: { texto: 'Cancelada', cor: 'vermelho' },
  };
  const pilulaStatus = (status) => {
    const s = STATUS_ENTREGA[status] || { texto: status, cor: 'cinza' };
    return `<span class="pilula ${s.cor}">${escapar(s.texto)}</span>`;
  };

  // ------------------------------------------------------------------ estrutura da página
  // Menu de cada perfil. A transportadora vê as cargas para cotar e a frota;
  // comprador, fornecedor e administrador acompanham solicitações e entregas.
  const MENUS = {
    transportadora: [
      ['fretes', 'fretes.html', 'lista', 'Solicitações de frete'],
      ['frota', 'frota.html', 'usuario', 'Minha frota'],
      ['transportadoras', 'transportadoras.html', 'balanca', 'Ranking'],
    ],
    outros: [
      ['solicitacoes', 'solicitacoes.html', 'lista', 'Solicitações de frete'],
      ['entregas', 'index.html', 'caminhao', 'Entregas'],
      ['transportadoras', 'transportadoras.html', 'balanca', 'Transportadoras'],
    ],
  };
  const inicioDoPerfil = (perfil) => (perfil === 'transportadora' ? 'fretes.html' : 'solicitacoes.html');

  function montarLateral(ativo) {
    const s = sessao();
    const itens = MENUS[s && s.usuario.perfil === 'transportadora' ? 'transportadora' : 'outros'];
    document.getElementById('lateral').innerHTML = `
      <div class="marca">${icone('folha', '')}<span>Portal B2B</span></div>
      <ul class="menu">
        ${itens.map(([id, href, ic, texto]) => `<li><a href="${href}" class="${ativo === id ? 'ativo' : ''}">${icone(ic)}${texto}</a></li>`).join('')}
      </ul>
      <div class="rodape">Grupo 5 · Logística e Transporte<br>Ambiente de desenvolvimento</div>`;
  }

  // ------------------------------------------------------------------ janela de diálogo (no lugar de confirm())
  function modal({ titulo, conteudo, botoes = [] }) {
    const fundo = document.createElement('div');
    fundo.className = 'modal-fundo';
    fundo.innerHTML = `<div class="cartao modal" role="dialog" aria-modal="true" aria-labelledby="modal-titulo">
      <h2 id="modal-titulo">${escapar(titulo)}</h2><div class="modal-corpo">${conteudo}</div>
      <div class="modal-acoes">${botoes.map((b, i) => `<button type="button" class="botao ${b.classe || ''}" data-i="${i}">${escapar(b.texto)}</button>`).join('')}</div></div>`;
    const fechar = () => fundo.remove();
    fundo.addEventListener('click', (ev) => { if (ev.target === fundo) fechar(); });
    document.addEventListener('keydown', function esc(ev) {
      if (ev.key === 'Escape') { fechar(); document.removeEventListener('keydown', esc); }
    });
    fundo.querySelectorAll('.modal-acoes button').forEach((b) => b.addEventListener('click', async () => {
      const acao = botoes[Number(b.dataset.i)].acao;
      if (!acao) { fechar(); return; }
      b.disabled = true;
      try { if ((await acao(fundo)) !== false) fechar(); } finally { b.disabled = false; }
    }));
    document.body.appendChild(fundo);
    const primeiro = fundo.querySelector('input, textarea, select, .modal-acoes .primario');
    if (primeiro) primeiro.focus();
    return { fechar, elemento: fundo };
  }

  // ------------------------------------------------------------------ download autenticado (PDF)
  async function baixar(caminho, nomeArquivo) {
    const s = sessao();
    const resposta = await fetch(caminho, { headers: s ? { Authorization: `Bearer ${s.token}` } : {} });
    if (!resposta.ok) {
      const problema = await resposta.json().catch(() => ({ title: 'Erro', detail: `HTTP ${resposta.status}` }));
      throw new ErroApi({ ...problema, status: resposta.status });
    }
    const url = URL.createObjectURL(await resposta.blob());
    const link = document.createElement('a');
    link.href = url;
    link.download = nomeArquivo;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  function montarTopo() {
    const s = sessao();
    const iniciais = s.usuario.nome.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();
    const comSino = ['comprador', 'fornecedor'].includes(s.usuario.perfil);
    document.getElementById('topo').innerHTML = `
      <div class="relogio" id="relogio" title="Hora do módulo de logística (pode ser acelerada pelo administrador)">
        ${icone('relogio')}<span class="hora" id="relogio-hora">—</span><span class="fator" id="relogio-fator">1×</span>
        ${s.usuario.perfil === 'admin' ? `<span class="velocidades" id="velocidades">
          ${[1, 360, 3600].map((f) => `<button type="button" data-fator="${f}">${f}×</button>`).join('')}</span>` : ''}
      </div>
      ${comSino ? `<div class="ancora"><button type="button" class="botao-icone" id="sino" aria-label="Notificações">
          ${icone('sino')}<span class="contador" id="sino-contador" hidden>0</span></button>
          <div class="painel-flutuante" id="painel-notificacoes" hidden></div></div>` : ''}
      <div class="ancora">
        <button type="button" class="usuario" id="menu-usuario" aria-haspopup="true">
          <span class="avatar">${escapar(iniciais)}</span>
          <span><strong>${escapar(s.usuario.nome)}</strong><small>${escapar(s.usuario.perfil)} · ${escapar(s.usuario.empresaNome)}</small></span>
        </button>
        <div class="painel-flutuante" id="painel-usuario" hidden></div>
      </div>`;

    document.getElementById('menu-usuario').addEventListener('click', alternarMenuUsuario);
    if (comSino) {
      document.getElementById('sino').addEventListener('click', alternarNotificacoes);
      atualizarSino();
      setInterval(atualizarSino, 10000);
    }
    const velocidades = document.getElementById('velocidades');
    if (velocidades) {
      velocidades.addEventListener('click', async (ev) => {
        const botao = ev.target.closest('button[data-fator]');
        if (!botao) return;
        try {
          await api('/api/v1/logistica/admin/relogio', { metodo: 'POST', corpo: { fator: Number(botao.dataset.fator) } });
          atualizarRelogio();
          avisoRapido(`Relógio do módulo em ${Number(botao.dataset.fator).toLocaleString('pt-BR')}×`);
        } catch (erro) { avisoRapido(`Não foi possível mudar o relógio: ${erro.message}`, true); }
      });
    }
    atualizarRelogio();
    setInterval(atualizarRelogio, 5000);
    document.addEventListener('click', (ev) => {
      document.querySelectorAll('.painel-flutuante').forEach((p) => {
        if (!p.parentElement.contains(ev.target)) p.hidden = true;
      });
    });
  }

  // Aviso curto no canto da tela (em vez de alert(), que trava a página).
  function avisoRapido(texto, erro = false) {
    const aviso = document.createElement('div');
    aviso.className = `aviso-rapido${erro ? ' erro' : ''}`;
    aviso.setAttribute('role', erro ? 'alert' : 'status');
    aviso.textContent = texto;
    document.body.appendChild(aviso);
    setTimeout(() => aviso.remove(), 4000);
  }

  // ------------------------------------------------------------------ relógio do módulo
  const relogio = { horaDoModulo: null, fator: 1 };
  async function atualizarRelogio() {
    try {
      const r = await api('/api/v1/logistica/relogio');
      relogio.horaDoModulo = r.horaDoModulo;
      relogio.fator = r.fator;
      document.getElementById('relogio-hora').textContent = formato.completa(r.horaDoModulo);
      const fator = document.getElementById('relogio-fator');
      fator.textContent = `${Number(r.fator).toLocaleString('pt-BR')}×`;
      fator.classList.toggle('rapido', r.fator > 1);
      document.querySelectorAll('#velocidades button').forEach((b) => b.classList.toggle('ativo', Number(b.dataset.fator) === r.fator));
    } catch { /* o relógio é só informativo */ }
  }

  // ------------------------------------------------------------------ notificações
  async function atualizarSino() {
    try {
      const r = await api('/api/v1/logistica/notificacoes?lida=false&size=1');
      const contador = document.getElementById('sino-contador');
      contador.textContent = r.naoLidas > 99 ? '99+' : r.naoLidas;
      contador.hidden = r.naoLidas === 0;
    } catch { /* idem */ }
  }

  async function alternarNotificacoes() {
    const painel = document.getElementById('painel-notificacoes');
    if (!painel.hidden) { painel.hidden = true; return; }
    painel.hidden = false;
    painel.innerHTML = '<div class="vazio">Carregando…</div>';
    try {
      const r = await api('/api/v1/logistica/notificacoes?size=15');
      painel.innerHTML = `<h3>Notificações</h3>${r.items.length ? r.items.map((n) => `
        <button type="button" class="notificacao ${n.lida ? '' : 'nao-lida'}" data-id="${escapar(n.id)}" data-pedido="${escapar(n.pedido_id || '')}">
          <strong>${escapar(n.titulo)}</strong><p>${escapar(n.mensagem)}</p><time>${formato.completa(n.criada_em)}</time>
        </button>`).join('') : '<div class="vazio">Nenhuma notificação.</div>'}`;
      painel.querySelectorAll('.notificacao').forEach((botao) => botao.addEventListener('click', () => abrirNotificacao(botao)));
    } catch (erro) { painel.innerHTML = erroHtml(erro); }
  }

  async function abrirNotificacao(botao) {
    try {
      await api(`/api/v1/logistica/notificacoes/${encodeURIComponent(botao.dataset.id)}`, { metodo: 'PATCH', corpo: { lida: true } });
      botao.classList.remove('nao-lida');
      atualizarSino();
      if (botao.dataset.pedido) {
        const entrega = await api(`/api/v1/logistica/pedidos/${encodeURIComponent(botao.dataset.pedido)}/entrega`);
        location.href = `entrega.html?id=${encodeURIComponent(entrega.id)}`;
      }
    } catch { /* pedido ainda sem entrega: fica só marcada como lida */ }
  }

  // ------------------------------------------------------------------ usuário e login de demonstração
  async function opcoesDeUsuario() {
    const usuarios = await api('/api/v1/usuarios/demonstracao');
    return usuarios.map((u) => `
      <button type="button" class="opcao-usuario" data-id="${escapar(u.id)}">
        <span class="avatar">${escapar(u.nome.split(' ').map((p) => p[0]).slice(0, 2).join(''))}</span>
        <span><strong>${escapar(u.nome)}</strong><small>${escapar(u.perfil)} · ${escapar(u.empresaNome)}</small></span>
      </button>`).join('');
  }

  async function entrarComo(usuarioId) {
    const r = await api('/api/v1/usuarios/demonstracao/login', { metodo: 'POST', corpo: { usuarioId } });
    salvarSessao({ token: r.accessToken, usuario: r.usuario });
    // Troca de perfil: a página atual pode não servir para o novo perfil.
    const pagina = location.pathname.split('/').pop() || 'index.html';
    const daTransportadora = ['fretes.html', 'frota.html'].includes(pagina);
    const ehTransportadora = r.usuario.perfil === 'transportadora';
    if (pagina !== 'transportadoras.html' && daTransportadora !== ehTransportadora) {
      location.href = inicioDoPerfil(r.usuario.perfil);
    } else {
      location.reload();
    }
  }

  async function alternarMenuUsuario() {
    const painel = document.getElementById('painel-usuario');
    if (!painel.hidden) { painel.hidden = true; return; }
    painel.hidden = false;
    try {
      painel.innerHTML = `<h3>Trocar de usuário (demonstração)</h3>${await opcoesDeUsuario()}
        <button type="button" class="opcao-usuario" id="botao-sair">${icone('sair')}<span><strong>Sair</strong></span></button>`;
      painel.querySelectorAll('.opcao-usuario[data-id]').forEach((b) => b.addEventListener('click', () => entrarComo(b.dataset.id)));
      document.getElementById('botao-sair').addEventListener('click', sair);
    } catch (erro) { painel.innerHTML = erroHtml(erro); }
  }

  async function mostrarLogin() {
    if (document.getElementById('tela-login')) return;
    const tela = document.createElement('div');
    tela.className = 'tela-login';
    tela.id = 'tela-login';
    tela.innerHTML = `<div class="cartao" role="dialog" aria-modal="true" aria-labelledby="titulo-login">
      <h2 id="titulo-login">Entrar no portal</h2>
      <p>Ambiente de desenvolvimento: escolha um usuário de demonstração. No portal real, o login é feito pelo serviço de Autenticação.</p>
      <div class="opcoes" id="opcoes-login"><div class="carregando">Carregando…</div></div></div>`;
    document.body.appendChild(tela);
    const opcoes = document.getElementById('opcoes-login');
    try {
      opcoes.innerHTML = await opcoesDeUsuario();
      opcoes.querySelectorAll('.opcao-usuario').forEach((b) => b.addEventListener('click', () => entrarComo(b.dataset.id)));
    } catch (erro) { opcoes.innerHTML = erroHtml(erro); }
  }

  // ------------------------------------------------------------------ início
  function iniciar({ ativo, perfis, aoEntrar }) {
    montarLateral(ativo);
    const s = sessao();
    if (!s) { mostrarLogin(); return; }
    if (perfis && !perfis.includes(s.usuario.perfil)) {
      location.replace(inicioDoPerfil(s.usuario.perfil));
      return;
    }
    montarTopo();
    aoEntrar(s);
  }

  return {
    iniciar, api, icone, escapar, erroHtml, formato, pilulaStatus, STATUS_ENTREGA, relogio, sessao, avisoRapido,
    modal, baixar, inicioDoPerfil,
  };
})();
