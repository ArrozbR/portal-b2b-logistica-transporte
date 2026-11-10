/* Solicitações de frete do comprador (e do fornecedor/admin): leva à comparação. Atualiza a cada 5 s. */
(() => {
  const { api, escapar, erroHtml, formato } = Portal;
  const STATUS = {
    ABERTA: ['Aguardando cotações', 'azul'],
    COTADA: ['Escolha o frete', 'verde'],
    SEM_COTACAO: ['Sem cotação ainda', 'ambar'],
    SELECIONADA: ['Frete escolhido', 'cinza'],
    INDISPONIVEL: ['Frete indisponível', 'vermelho'],
    CANCELADA: ['Cancelada', 'vermelho'],
  };
  const GRUPOS = { todas: null, escolher: ['COTADA', 'ABERTA', 'SEM_COTACAO'], escolhidas: ['SELECIONADA'] };
  let filtro = 'todas';

  function prazo(s, horaDoModulo) {
    if (!['ABERTA', 'COTADA', 'SEM_COTACAO'].includes(s.status)) {
      return s.escolhida_em ? `<span class="suave">Escolhido em</span><br>${formato.curta(s.escolhida_em)}` : '—';
    }
    const restante = new Date(s.prazo_decisao_em) - new Date(horaDoModulo);
    const urgente = restante < 2 * 3600 * 1000;
    return `<span class="suave">Escolher até</span><br><span class="prazo-escolha ${urgente ? 'urgente' : ''}">${formato.curta(s.prazo_decisao_em)}</span>
      <br><span class="suave">${formato.relativo(s.prazo_decisao_em, horaDoModulo)}</span>`;
  }

  function linha(s, horaDoModulo) {
    const [texto, cor] = STATUS[s.status] || [s.status, 'cinza'];
    return `<tr data-id="${escapar(s.id)}" tabindex="0">
      <td><strong>${escapar(s.pedido_id)}</strong><br><span class="suave">aberta ${formato.curta(s.aberta_em)}</span></td>
      <td><span class="rota">${escapar(s.origem_cidade)} - ${escapar(s.origem_uf)} → ${escapar(s.destino_cidade)} - ${escapar(s.destino_uf)}</span>
        <br><span class="suave">${Number(s.distancia_km).toLocaleString('pt-BR')} km</span></td>
      <td class="opcional">${escapar(s.produto_nome)}<br><span class="suave">${formato.toneladas(s.peso_kg)} · ${formato.tipoCarga(s.tipo_carga)}</span></td>
      <td><span class="pilula ${cor}">${texto}</span>${s.criterio === 'AUTOMATICO_MENOR_PRECO' ? '<br><span class="suave">regra automática</span>' : ''}</td>
      <td>${prazo(s, horaDoModulo)}</td>
    </tr>`;
  }

  async function carregar() {
    const lista = document.getElementById('lista');
    try {
      const [r, relogio] = await Promise.all([
        api('/api/v1/logistica/solicitacoes?size=100'),
        api('/api/v1/logistica/relogio'),
      ]);
      const grupo = GRUPOS[filtro];
      const itens = grupo ? r.items.filter((s) => grupo.includes(s.status)) : r.items;
      document.getElementById('mensagem').innerHTML = '';
      lista.className = '';
      if (!itens.length) {
        lista.innerHTML = `<div class="vazio-grande">Nenhuma solicitação ${filtro === 'todas' ? 'ainda' : 'neste filtro'}.
          ${filtro === 'todas' ? `<br>As solicitações chegam do grupo de Pedidos. No ambiente de desenvolvimento, publique um pedido de teste:<br>
          <code>docker compose exec logistica-1 python -m comum.ferramentas.publicar_pedido_falso</code>` : ''}</div>`;
        return;
      }
      lista.innerHTML = `<table class="tabela"><thead><tr><th>Pedido</th><th>Rota</th><th class="opcional">Carga</th>
        <th>Situação</th><th>Prazo</th></tr></thead><tbody>${itens.map((s) => linha(s, relogio.horaDoModulo)).join('')}</tbody></table>`;
      lista.querySelectorAll('tbody tr').forEach((tr) => {
        const abrir = () => { location.href = `comparacao.html?id=${encodeURIComponent(tr.dataset.id)}`; };
        tr.addEventListener('click', abrir);
        tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(); });
      });
    } catch (erro) {
      lista.className = '';
      lista.innerHTML = '';
      document.getElementById('mensagem').innerHTML = erroHtml(erro);
    }
  }

  Portal.iniciar({
    ativo: 'solicitacoes',
    perfis: ['comprador', 'fornecedor', 'admin'],
    aoEntrar() {
      document.getElementById('conteudo').innerHTML = `
        <div class="cabecalho"><div><h1>Solicitações de frete</h1>
          <p>Cada pedido abre uma solicitação. Compare as cotações das transportadoras e escolha o frete.</p></div></div>
        <div class="filtros" id="filtros">
          <button type="button" data-filtro="todas" class="ativo">Todas</button>
          <button type="button" data-filtro="escolher">Aguardando escolha</button>
          <button type="button" data-filtro="escolhidas">Frete escolhido</button>
        </div>
        <div id="mensagem"></div>
        <section class="cartao" aria-live="polite"><div id="lista" class="carregando">Carregando solicitações…</div></section>`;
      document.getElementById('filtros').addEventListener('click', (ev) => {
        const botao = ev.target.closest('button[data-filtro]');
        if (!botao) return;
        filtro = botao.dataset.filtro;
        document.querySelectorAll('#filtros button').forEach((b) => b.classList.toggle('ativo', b === botao));
        carregar();
      });
      carregar();
      setInterval(carregar, 5000);
    },
  });
})();
