/*
 * Comparação das cotações de uma solicitação (decisões D5 e D6).
 *
 * Cartões com selos (mais barata, mais rápida, mais pontual, recomendada pela
 * regra), pontualidade de cada transportadora e gráfico preço × prazo. O
 * comprador escolhe uma cotação ou clica em "automático" (regra do menor
 * preço). Atualiza a cada 5 s: cotações digitadas podem chegar a qualquer momento.
 */
(() => {
  const { api, escapar, erroHtml, formato, icone, modal, avisoRapido } = Portal;
  const solicitacaoId = new URLSearchParams(location.search).get('id');
  let ultimo = null;

  const SELOS = {
    MAIS_BARATA: ['Mais barata', 'verde'],
    MAIS_RAPIDA: ['Mais rápida', 'azul'],
    MAIS_PONTUAL: ['Mais pontual', 'roxo'],
    RECOMENDADA_PELA_REGRA: ['✓ Recomendada pela regra', 'verde'],
  };
  const STATUS_SOLICITACAO = {
    ABERTA: 'Aguardando cotações', COTADA: 'Aguardando a sua escolha', SEM_COTACAO: 'Sem cotação ainda',
    SELECIONADA: 'Frete escolhido', INDISPONIVEL: 'Frete indisponível', CANCELADA: 'Cancelada',
  };

  // ------------------------------------------------------------------ cartões
  function chips(c) {
    const lista = c.selos.map((s) => `<span class="chip ${SELOS[s][1]}">${SELOS[s][0]}</span>`);
    if (c.origem_cotacao === 'DIGITADA') lista.push('<span class="chip ambar">Cotação digitada</span>');
    if (c.status === 'VIAGEM_RECUSADA') lista.push('<span class="chip">Recusou a viagem (sem frota)</span>');
    if (c.status === 'RECUSADA_TARDE') lista.push('<span class="chip">Chegou depois da escolha</span>');
    if (c.escolhida) lista.push('<span class="chip verde">Escolhida</span>');
    return lista.join('');
  }

  function pontualidade(d) {
    if (!d.entregas) return '<span>Pontualidade: <b>sem histórico</b></span>';
    return `<span class="pontualidade">Pontualidade: <span class="barra"><span style="width:${Math.round(d.pct_no_prazo * 100)}%"></span></span>
      <b>${formato.porcentagem(d.pct_no_prazo)}</b> (${d.entregas} ${d.entregas === 1 ? 'entrega' : 'entregas'})</span>`;
  }

  function cartao(c, podeEscolher) {
    const classes = ['cartao', 'cotacao'];
    if (c.escolhida) classes.push('escolhida');
    else if (c.selos.includes('RECOMENDADA_PELA_REGRA') && podeEscolher) classes.push('recomendada');
    if (c.status !== 'VALIDA') classes.push('inativa');
    return `<article class="${classes.join(' ')}">
      <div>
        <h3>${escapar(c.transportadora_nome || c.transportadora_id)} <span class="chips">${chips(c)}</span></h3>
        <div class="metricas">
          <span><b>${c.prazo_dias}</b> dias úteis</span>
          <span>entrega <b>${formato.data(c.data_entrega_prevista)}</b></span>
          <span><b>${formato.precoTkm(c.preco_t_km)}</b></span>
          ${pontualidade(c.desempenho)}
          ${c.valida_ate ? `<span>válida até ${formato.curta(c.valida_ate)}</span>` : ''}
        </div>
      </div>
      <div class="preco">${formato.moeda(c.preco)}</div>
      ${c.observacoes ? `<div class="obs">“${escapar(c.observacoes)}”</div>` : ''}
      ${podeEscolher && c.status === 'VALIDA' ? `<div class="acao"><button type="button" class="botao primario pequeno" data-escolher="${escapar(c.id)}">Escolher esta cotação</button></div>` : ''}
    </article>`;
  }

  // ------------------------------------------------------------------ gráfico preço × prazo (SVG)
  function grafico(cotacoes) {
    const pontos = cotacoes.filter((c) => c.status === 'VALIDA' || c.escolhida);
    if (pontos.length === 0) return '<div class="vazio">Sem cotações para comparar ainda.</div>';
    const L = 400, A = 260, m = { e: 64, d: 18, t: 16, b: 40 };
    const prazos = pontos.map((c) => c.prazo_dias);
    const precos = pontos.map((c) => Number(c.preco));
    const xMin = Math.max(0, Math.min(...prazos) - 1), xMax = Math.max(...prazos) + 1;
    const folga = Math.max((Math.max(...precos) - Math.min(...precos)) * 0.15, Math.max(...precos) * 0.05);
    const yMin = Math.max(0, Math.min(...precos) - folga), yMax = Math.max(...precos) + folga;
    const x = (v) => m.e + ((v - xMin) / (xMax - xMin)) * (L - m.e - m.d);
    const y = (v) => A - m.b - ((v - yMin) / (yMax - yMin)) * (A - m.t - m.b);
    const ticksY = [0, 1, 2, 3].map((i) => yMin + ((yMax - yMin) * i) / 3);
    const ticksX = [];
    for (let d = Math.ceil(xMin); d <= xMax; d += Math.max(1, Math.ceil((xMax - xMin) / 6))) ticksX.push(d);
    const cor = (c) => (c.escolhida ? '#4d7c0f' : c.selos.includes('RECOMENDADA_PELA_REGRA') ? '#84cc16' : '#94a3b8');
    const reais = (v) => `R$ ${Math.round(v).toLocaleString('pt-BR')}`;
    return `<svg viewBox="0 0 ${L} ${A}" role="img" aria-label="Gráfico de preço por prazo das cotações">
      ${ticksY.map((v) => `<line class="grade" x1="${m.e}" x2="${L - m.d}" y1="${y(v)}" y2="${y(v)}"/>
        <text x="${m.e - 8}" y="${y(v) + 4}" text-anchor="end">${reais(v)}</text>`).join('')}
      ${ticksX.map((d) => `<text x="${x(d)}" y="${A - m.b + 16}" text-anchor="middle">${d}</text>`).join('')}
      <line class="eixo" x1="${m.e}" x2="${L - m.d}" y1="${A - m.b}" y2="${A - m.b}"/>
      <line class="eixo" x1="${m.e}" x2="${m.e}" y1="${m.t}" y2="${A - m.b}"/>
      <text x="${(m.e + L - m.d) / 2}" y="${A - 6}" text-anchor="middle">Prazo (dias úteis) →</text>
      ${pontos.map((c) => {
        const nome = (c.transportadora_nome || c.transportadora_id).split(' ')[0];
        return `<g><title>${escapar(c.transportadora_nome)}: ${formato.moeda(c.preco)}, ${c.prazo_dias} dias úteis</title>
          <circle cx="${x(c.prazo_dias)}" cy="${y(Number(c.preco))}" r="${c.escolhida ? 9 : 7}" fill="${cor(c)}"/>
          <text class="rotulo" x="${x(c.prazo_dias) + 11}" y="${y(Number(c.preco)) + 4}">${escapar(nome)}</text></g>`;
      }).join('')}
    </svg>
    <div class="legenda-grafico"><span><i style="background:#84cc16"></i>Recomendada pela regra</span>
      <span><i style="background:#4d7c0f"></i>Escolhida</span><span><i style="background:#94a3b8"></i>Outras</span>
      <span>Mais embaixo = mais barata · mais à esquerda = mais rápida</span></div>`;
  }

  // ------------------------------------------------------------------ escolha
  function confirmarEscolha(cotacao) {
    const automatica = !cotacao;
    const chave = crypto.randomUUID(); // a mesma chave em todas as tentativas desta escolha
    const recomendada = ultimo.cotacoes.find((c) => c.selos.includes('RECOMENDADA_PELA_REGRA'));
    const alvo = cotacao || recomendada;
    modal({
      titulo: automatica ? 'Escolher automaticamente?' : 'Confirmar a escolha do frete',
      conteudo: `<p>${automatica ? 'A regra do menor preço (desempate pelo menor prazo) escolhe:' : 'Você vai contratar:'}</p>
        <dl class="detalhe-carga"><dt>Transportadora</dt><dd>${escapar(alvo.transportadora_nome)}</dd>
        <dt>Valor do frete</dt><dd>${formato.moeda(alvo.preco)}</dd>
        <dt>Prazo</dt><dd>${alvo.prazo_dias} dias úteis (até ${formato.data(alvo.data_entrega_prevista)})</dd></dl>
        <p class="suave">Depois de escolhido, o frete não pode ser trocado por esta tela.</p><div id="erro-escolha"></div>`,
      botoes: [
        { texto: 'Voltar' },
        {
          texto: automatica ? 'Escolher automaticamente' : 'Confirmar escolha',
          classe: 'primario',
          async acao(janela) {
            try {
              const r = await api(`/api/v1/logistica/solicitacoes/${encodeURIComponent(solicitacaoId)}/selecionar-frete`, {
                metodo: 'POST', corpo: automatica ? { modo: 'AUTOMATICO' } : { cotacaoId: cotacao.id },
                cabecalhos: { 'Idempotency-Key': chave },
              });
              avisoRapido(`Frete escolhido: ${r.transportadoraNome || r.transportadoraId}`);
              carregar();
              return true;
            } catch (erro) {
              janela.querySelector('#erro-escolha').innerHTML = erroHtml(erro);
              return false;
            }
          },
        },
      ],
    });
  }

  // ------------------------------------------------------------------ página
  function render(r) {
    const s = r.solicitacao;
    const validas = r.cotacoes.filter((c) => c.status === 'VALIDA');
    const escolhida = r.cotacoes.find((c) => c.escolhida);
    const restante = new Date(s.prazo_decisao_em) - new Date(r.horaDoModulo);
    const aberta = ['ABERTA', 'COTADA', 'SEM_COTACAO'].includes(s.status);

    let aviso = '';
    if (escolhida) {
      aviso = `<div class="aviso info">${icone('check')}<div><strong>Frete escolhido:</strong> ${escapar(escolhida.transportadora_nome)},
        ${formato.moeda(escolhida.preco)}, ${escolhida.prazo_dias} dias úteis
        (${s.criterio === 'ESCOLHA_COMPRADOR' ? 'escolha do comprador' : 'regra automática'}).
        ${r.entregaId ? ` <a href="entrega.html?id=${encodeURIComponent(r.entregaId)}"><strong>Acompanhar a entrega →</strong></a>` : ''}</div></div>`;
    } else if (s.status === 'INDISPONIVEL' || s.status === 'CANCELADA') {
      aviso = `<div class="aviso erro">${icone('alerta')}<div><strong>${STATUS_SOLICITACAO[s.status]}.</strong>
        ${s.status === 'INDISPONIVEL' ? 'Nenhuma transportadora pôde levar a carga; o pedido será cancelado.' : 'O pedido foi cancelado.'}</div></div>`;
    } else if (!r.podeEscolher && aberta && Portal.sessao().usuario.perfil === 'fornecedor') {
      aviso = '<div class="aviso info">Você está vendo como fornecedor: quem escolhe o frete é o comprador.</div>';
    }

    document.getElementById('conteudo').innerHTML = `
      <a class="voltar" href="solicitacoes.html">${icone('seta')} Voltar para solicitações</a>
      <div class="cabecalho"><div><h1>Pedido #${escapar(s.pedido_id)}</h1>
        <p>Compare as cotações e escolha a transportadora. Se ninguém escolher até o prazo, vale a de menor preço.</p></div></div>
      ${aviso}
      <section class="cartao faixa-info">
        <div><small>Rota</small><strong>${escapar(s.origem_cidade)} - ${escapar(s.origem_uf)} → ${escapar(s.destino_cidade)} - ${escapar(s.destino_uf)}</strong></div>
        <div><small>Carga</small><strong>${escapar(s.produto_nome)} · ${formato.toneladas(s.peso_kg)} · ${formato.tipoCarga(s.tipo_carga)}</strong></div>
        <div><small>Distância</small><strong>${Number(s.distancia_km).toLocaleString('pt-BR')} km</strong></div>
        <div><small>Coleta prevista</small><strong>${formato.data(s.data_coleta_prevista)}</strong></div>
        <div><small>${aberta ? 'Escolher até' : 'Situação'}</small><strong class="${aberta && restante < 7200000 ? 'prazo-escolha urgente' : ''}">
          ${aberta ? `${formato.curta(s.prazo_decisao_em)} · ${formato.relativo(s.prazo_decisao_em, r.horaDoModulo).toLowerCase()}` : STATUS_SOLICITACAO[s.status]}</strong></div>
      </section>
      <div class="grade-comparacao">
        <section class="lista-cotacoes" aria-live="polite">
          ${r.cotacoes.length ? r.cotacoes.map((c) => cartao(c, r.podeEscolher)).join('')
            : `<div class="cartao vazio-grande">Nenhuma cotação ainda. As transportadoras simuladas respondem em segundos;
               as reais cotam pela tela "Solicitações de frete".</div>`}
        </section>
        <div>
          <section class="cartao"><h2>${icone('balanca')} Preço × prazo</h2><div class="grafico">${grafico(r.cotacoes)}</div></section>
          ${r.podeEscolher && validas.length ? `<section class="cartao" style="margin-top:18px"><h2>${icone('check')} Escolha automática</h2>
            <div class="corpo"><p class="suave" style="margin-top:0">Menor preço; em empate, menor prazo; depois a mais pontual.
            É o que acontece se o prazo de escolha acabar.</p>
            <button type="button" class="botao largo" id="automatico">Escolher automaticamente</button></div></section>` : ''}
        </div>
      </div>`;

    document.querySelectorAll('[data-escolher]').forEach((b) => b.addEventListener('click', () => {
      confirmarEscolha(ultimo.cotacoes.find((c) => c.id === b.dataset.escolher));
    }));
    const automatico = document.getElementById('automatico');
    if (automatico) automatico.addEventListener('click', () => confirmarEscolha(null));
  }

  async function carregar() {
    try {
      ultimo = await api(`/api/v1/logistica/solicitacoes/${encodeURIComponent(solicitacaoId)}/comparacao`);
      if (!document.querySelector('.modal-fundo')) render(ultimo); // não redesenha com a confirmação aberta
    } catch (erro) {
      document.getElementById('conteudo').innerHTML = `<a class="voltar" href="solicitacoes.html">${icone('seta')} Voltar para solicitações</a>${erroHtml(erro)}`;
    }
  }

  Portal.iniciar({
    ativo: 'solicitacoes',
    perfis: ['comprador', 'fornecedor', 'admin'],
    aoEntrar() {
      if (!solicitacaoId) { location.replace('solicitacoes.html'); return; }
      carregar();
      setInterval(carregar, 5000);
    },
  });
})();
