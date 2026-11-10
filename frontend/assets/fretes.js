/*
 * Solicitações de frete da transportadora (mockup portal_b2b_06_fretes.png, decisão D3).
 *
 * Lista as cargas compatíveis com a transportadora do usuário e permite enviar
 * uma cotação digitada. Validações do grupo de UX (UX-FRT-06): valor maior que
 * zero, entrega depois da coleta e validade no futuro (hora do módulo).
 */
(() => {
  const { api, escapar, erroHtml, formato, icone, avisoRapido } = Portal;
  const SITUACAO = {
    ACEITANDO_COTACOES: ['Aceitando cotações', 'verde'],
    COTACAO_ENVIADA: ['Cotação enviada', 'azul'],
    VENCEU: ['Você venceu', 'verde'],
    OUTRA_VENCEU: ['Outra transportadora venceu', 'cinza'],
    CANCELADA: ['Pedido cancelado', 'vermelho'],
    ENCERRADA: ['Encerrada', 'cinza'],
  };
  const estado = { cargas: [], selecionada: null, horaDoModulo: null, filtros: { origem: '', destino: '', tipo: '' }, todas: false };

  // "2026-11-20T12:00:00Z" → "2026-11-20T09:00" (campo datetime-local, horário de Brasília)
  function paraCampoDataHora(iso) {
    const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
    }).formatToParts(new Date(iso)).map((x) => [x.type, x.value]));
    return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
  }
  const diaSeguinte = (isoData) => new Date(new Date(`${isoData}T00:00:00Z`).getTime() + 86400000).toISOString().slice(0, 10);
  const normalizar = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  function filtradas() {
    const { origem, destino, tipo } = estado.filtros;
    return estado.cargas.filter((c) => (!origem || normalizar(`${c.origem_cidade} ${c.origem_uf}`).includes(normalizar(origem)))
      && (!destino || normalizar(`${c.destino_cidade} ${c.destino_uf}`).includes(normalizar(destino)))
      && (!tipo || c.tipo_carga === tipo));
  }

  // ------------------------------------------------------------------ lista
  function renderLista() {
    const itens = filtradas();
    document.getElementById('total').textContent = `Mostrando ${itens.length} ${itens.length === 1 ? 'carga encontrada' : 'cargas encontradas'}`;
    const corpo = document.getElementById('cargas');
    if (!itens.length) {
      corpo.innerHTML = `<div class="vazio-grande">Nenhuma carga compatível com a sua frota agora.<br>
        As cargas aparecem quando um pedido é criado; publique um de teste com
        <code>docker compose exec logistica-1 python -m comum.ferramentas.publicar_pedido_falso</code></div>`;
      return;
    }
    corpo.innerHTML = `<table class="tabela"><thead><tr><th>Origem → Destino</th><th>Carga</th><th class="opcional">Peso</th>
      <th>Data de coleta</th><th class="opcional">Cotar até</th><th>Status</th></tr></thead><tbody>
      ${itens.map((c) => {
        const [texto, cor] = SITUACAO[c.situacao];
        return `<tr data-id="${escapar(c.id)}" tabindex="0" class="${estado.selecionada === c.id ? 'selecionada' : ''}">
          <td><span class="rota">${escapar(c.origem_cidade)} - ${escapar(c.origem_uf)} → ${escapar(c.destino_cidade)} - ${escapar(c.destino_uf)}</span></td>
          <td>${escapar(c.produto_nome)}<br><span class="suave">${formato.tipoCarga(c.tipo_carga)}</span></td>
          <td class="opcional">${formato.toneladas(c.peso_kg)}</td>
          <td>${formato.data(c.data_coleta_prevista)}</td>
          <td class="opcional">${formato.curta(c.prazo_decisao_em)}</td>
          <td><span class="pilula ${cor}">${texto}</span></td></tr>`;
      }).join('')}</tbody></table>`;
    corpo.querySelectorAll('tbody tr').forEach((tr) => {
      const selecionar = () => { estado.selecionada = tr.dataset.id; renderLista(); renderPainel(); };
      tr.addEventListener('click', selecionar);
      tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') selecionar(); });
    });
  }

  // ------------------------------------------------------------------ painel "Enviar cotação"
  function renderPainel() {
    const painel = document.getElementById('painel');
    const c = estado.cargas.find((x) => x.id === estado.selecionada);
    if (!c) {
      painel.innerHTML = `<h2>Enviar cotação</h2><p>Selecione uma carga na lista para ver os detalhes e cotar.</p>`;
      return;
    }
    const [texto, cor] = SITUACAO[c.situacao];
    const detalhes = `<dl class="detalhe-carga">
      <dt>Origem</dt><dd>${escapar(c.origem_cidade)} - ${escapar(c.origem_uf)}</dd>
      <dt>Destino</dt><dd>${escapar(c.destino_cidade)} - ${escapar(c.destino_uf)}</dd>
      <dt>Carga</dt><dd>${escapar(c.produto_nome)}</dd>
      <dt>Peso</dt><dd>${formato.toneladas(c.peso_kg)}</dd>
      <dt>Distância</dt><dd>${Number(c.distancia_km).toLocaleString('pt-BR')} km</dd>
      <dt>Data de coleta</dt><dd>${formato.data(c.data_coleta_prevista)}</dd>
      <dt>Cotar até</dt><dd>${formato.curta(c.prazo_decisao_em)}</dd>
      <dt>Status</dt><dd><span class="pilula ${cor}">${texto}</span></dd></dl>`;

    if (!c.pode_cotar) {
      painel.innerHTML = `<h2>Sua cotação</h2><p>${c.minha_cotacao_id ? 'Cotação enviada para esta carga.' : 'Esta carga não aceita mais cotações.'}</p>
        ${detalhes}
        ${c.minha_cotacao_id ? `<dl class="detalhe-carga"><dt>Valor</dt><dd>${formato.moeda(c.minha_cotacao_preco)}</dd>
          <dt>Prazo</dt><dd>${c.minha_cotacao_prazo} dias úteis (${formato.data(c.minha_cotacao_entrega)})</dd>
          <dt>Enviada em</dt><dd>${formato.curta(c.minha_cotacao_emitida_em)}</dd>
          <dt>Protocolo</dt><dd><code>${escapar(c.minha_cotacao_id.slice(0, 8))}</code></dd></dl>` : ''}`;
      return;
    }

    painel.innerHTML = `<h2>Enviar cotação</h2><p>Preencha os dados da sua proposta de frete.</p>${detalhes}
      <form id="form-cotacao" novalidate>
        <div class="campo" id="c-valor"><label for="valor">Valor do frete <span class="obrigatorio">*</span></label>
          <div class="com-prefixo"><span>R$</span><input id="valor" name="valor" type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="0,00" required></div></div>
        <div class="campo" id="c-entrega"><label for="entrega">Prazo estimado (data de entrega) <span class="obrigatorio">*</span></label>
          <input id="entrega" name="entrega" type="date" min="${diaSeguinte(c.data_coleta_prevista)}" required></div>
        <div class="campo" id="c-validade"><label for="validade">Validade da proposta <span class="obrigatorio">*</span></label>
          <input id="validade" name="validade" type="datetime-local" value="${paraCampoDataHora(c.prazo_decisao_em)}" required>
          <span class="ajuda">Hora do módulo; precisa ser depois de ${formato.completa(estado.horaDoModulo)}.</span></div>
        <div class="campo"><label for="observacoes">Observações</label>
          <textarea id="observacoes" name="observacoes" maxlength="500" placeholder="Informe condições, tipo de veículo, restrições ou demais informações (opcional)."></textarea>
          <div class="contador-caracteres" id="contador">0/500</div></div>
        <div id="erro-envio"></div>
        <button type="submit" class="botao primario largo">${icone('seta')} Enviar cotação</button>
      </form>`;
    const obs = document.getElementById('observacoes');
    obs.addEventListener('input', () => { document.getElementById('contador').textContent = `${obs.value.length}/500`; });
    document.getElementById('form-cotacao').addEventListener('submit', (ev) => { ev.preventDefault(); enviar(c); });
  }

  function marcarErro(id, mensagem) {
    const campo = document.getElementById(id);
    campo.classList.add('invalido');
    campo.insertAdjacentHTML('beforeend', `<span class="erro-campo">${escapar(mensagem)}</span>`);
  }

  async function enviar(c) {
    const form = document.getElementById('form-cotacao');
    form.querySelectorAll('.campo').forEach((campo) => campo.classList.remove('invalido'));
    form.querySelectorAll('.erro-campo').forEach((e) => e.remove());
    document.getElementById('erro-envio').innerHTML = '';

    const valor = Number(form.valor.value);
    const entrega = form.entrega.value;
    const validade = form.validade.value;
    let ok = true;
    if (!(valor > 0)) { marcarErro('c-valor', 'Informe um valor maior que zero.'); ok = false; }
    if (!entrega || entrega <= c.data_coleta_prevista) { marcarErro('c-entrega', 'A entrega precisa ser depois da data de coleta.'); ok = false; }
    if (!validade || new Date(`${validade}:00-03:00`) <= new Date(estado.horaDoModulo)) {
      marcarErro('c-validade', 'A validade precisa ser depois da hora atual do módulo.'); ok = false;
    }
    if (!ok) return;

    const botao = form.querySelector('button[type=submit]');
    botao.disabled = true;
    try {
      const r = await api(`/api/v1/transportadoras/solicitacoes/${encodeURIComponent(c.id)}/cotacoes`, {
        metodo: 'POST',
        corpo: { valor, dataEntregaPrevista: entrega, validaAte: `${validade}:00-03:00`, observacoes: form.observacoes.value.trim() || null },
      });
      avisoRapido(`Cotação enviada: ${formato.moeda(r.preco)}, ${r.prazoDias} dias úteis. Protocolo ${r.cotacaoId.slice(0, 8)}.`);
      await carregar(true);
    } catch (erro) {
      document.getElementById('erro-envio').innerHTML = erroHtml(erro);
      botao.disabled = false;
    }
  }

  // ------------------------------------------------------------------ dados
  async function carregar(redesenharPainel = false) {
    try {
      const r = await api(`/api/v1/transportadoras/solicitacoes?size=100&todas=${estado.todas}`);
      const antes = estado.cargas.find((c) => c.id === estado.selecionada);
      estado.cargas = r.items;
      estado.horaDoModulo = r.horaDoModulo;
      document.getElementById('mensagem').innerHTML = '';
      renderLista();
      const depois = estado.cargas.find((c) => c.id === estado.selecionada);
      const formTocado = document.getElementById('valor') && document.getElementById('valor').value;
      if (redesenharPainel || !antes || !depois || antes.situacao !== depois.situacao) {
        if (!formTocado || redesenharPainel || (depois && !depois.pode_cotar)) renderPainel();
      }
    } catch (erro) {
      document.getElementById('mensagem').innerHTML = erroHtml(erro);
    }
  }

  Portal.iniciar({
    ativo: 'fretes',
    perfis: ['transportadora'],
    async aoEntrar() {
      let nome = '';
      try { nome = (await api('/api/v1/transportadoras/minha')).nome; } catch { /* mostra a lista mesmo assim */ }
      document.getElementById('conteudo').innerHTML = `
        <div class="cabecalho"><div><h1>Solicitações de frete</h1>
          <p>Encontre cargas disponíveis e envie suas cotações${nome ? ` como <strong>${escapar(nome)}</strong>` : ''}.</p></div></div>
        <div id="mensagem"></div>
        <form class="cartao busca" id="busca">
          <div class="campo"><label for="f-origem">Origem</label><input id="f-origem" placeholder="Ex.: Sorriso - MT"></div>
          <div class="campo"><label for="f-destino">Destino</label><input id="f-destino" placeholder="Ex.: Santos - SP"></div>
          <div class="campo"><label for="f-tipo">Tipo de carga</label><select id="f-tipo"><option value="">Todos</option>
            <option value="GRANEL">Granel</option><option value="CARGA_SECA">Carga seca</option>
            <option value="REFRIGERADO">Refrigerada</option><option value="PERIGOSO">Perigosa</option></select></div>
          <button type="submit" class="botao primario">Buscar cargas</button>
        </form>
        <div class="grade-fretes">
          <section class="cartao">
            <div class="cabecalho-cartao"><div><h2>Cargas disponíveis</h2><span class="suave" id="total"></span></div>
              <label class="suave"><input type="checkbox" id="todas"> Mostrar encerradas</label></div>
            <div id="cargas" class="carregando">Carregando…</div>
          </section>
          <aside class="cartao painel-cotacao" id="painel" aria-live="polite"></aside>
        </div>`;
      document.getElementById('busca').addEventListener('submit', (ev) => {
        ev.preventDefault();
        estado.filtros = { origem: document.getElementById('f-origem').value.trim(),
          destino: document.getElementById('f-destino').value.trim(), tipo: document.getElementById('f-tipo').value };
        renderLista();
      });
      document.getElementById('todas').addEventListener('change', (ev) => { estado.todas = ev.target.checked; carregar(); });
      renderPainel();
      await carregar();
      setInterval(() => carregar(), 5000);
    },
  });
})();
