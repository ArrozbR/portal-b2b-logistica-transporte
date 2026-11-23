/* Solicitações de frete do comprador (e do fornecedor/admin): leva à comparação. Atualiza a cada 5 s.
   O admin tem o botão "Novo pedido de teste": o pedidos-falso (papel do grupo de Pedidos, D23)
   publica um pedido_criado, e a solicitação aparece aqui quando a logística consome o evento. */
(() => {
  const { api, escapar, erroHtml, formato, modal, avisoRapido } = Portal;
  const TIPOS = ['GRANEL', 'REFRIGERADO', 'CARGA_SECA', 'PERIGOSO'];
  let cidades = null;
  let comPedidosFalso = false;

  async function novoPedido() {
    try {
      cidades = cidades || await api('/api/v1/pedidos-falso/cidades');
    } catch (erro) { avisoRapido(`Não foi possível abrir o formulário: ${erro.message}`, true); return; }
    const opcoes = (padrao) => cidades.map((c) => {
      const valor = `${c.cidade}/${c.uf}`;
      return `<option value="${escapar(valor)}" ${valor === padrao ? 'selected' : ''}>${escapar(c.cidade)} - ${escapar(c.uf)}</option>`;
    }).join('');
    modal({
      titulo: 'Novo pedido de teste',
      conteudo: `<p class="suave">Faz o papel do grupo de Pedidos: publica um <code>pedido_criado</code> no Kafka.
        A logística abre a solicitação ao consumir o evento, e as transportadoras cotam em seguida.</p>
        <div class="linha-campos">
          <div class="campo"><label for="p-origem">Origem</label><select id="p-origem">${opcoes('Sorriso/MT')}</select></div>
          <div class="campo"><label for="p-destino">Destino</label><select id="p-destino">${opcoes('Santos/SP')}</select></div>
        </div>
        <div class="linha-campos">
          <div class="campo"><label for="p-tipo">Tipo de carga</label><select id="p-tipo">
            ${TIPOS.map((t) => `<option value="${t}">${formato.tipoCarga(t)}</option>`).join('')}</select></div>
          <div class="campo"><label for="p-peso">Peso (t) <span class="obrigatorio">*</span></label>
            <input id="p-peso" type="number" min="0.1" max="100" step="0.1" value="24"></div>
        </div>
        <div class="linha-campos">
          <div class="campo"><label for="p-produto">Produto <span class="obrigatorio">*</span></label><input id="p-produto" value="Soja em grão" maxlength="120"></div>
          <div class="campo"><label for="p-valor">Valor da carga (R$) <span class="obrigatorio">*</span></label>
            <input id="p-valor" type="number" min="0" step="100" value="192000"></div>
        </div>
        <div class="campo"><label><input type="checkbox" id="p-leilao"> Pedido de leilão</label>
          <span class="ajuda">O pedido nasce sem comprador nem destino, como na abertura do leilão. A solicitação
          de frete só abre quando o leilão fecha, 10 s depois (o destino acima é o do comprador vencedor).</span></div>
        <div id="erro-modal"></div>`,
      botoes: [{ texto: 'Cancelar' }, {
        texto: 'Criar pedido', classe: 'primario', async acao(janela) {
          const v = (id) => janela.querySelector(id).value.trim();
          const local = (texto) => { const [cidade, uf] = texto.split('/'); return { cidade, uf }; };
          const corpo = {
            origem: local(v('#p-origem')), destino: local(v('#p-destino')), tipoTransporte: v('#p-tipo'),
            pesoKg: Math.round(Number(v('#p-peso')) * 1000), produtoNome: v('#p-produto'), valorTotal: Number(v('#p-valor')),
            leilao: janela.querySelector('#p-leilao').checked, fechamentoEmSegundos: 10,
          };
          try {
            const r = await api('/api/v1/pedidos-falso/pedidos', { metodo: 'POST', corpo });
            if (corpo.leilao) {
              avisoRapido(`Leilão ${r.pedidoId} aberto. A solicitação aparece quando ele fechar, em ${r.fechamentoEmSegundos} s.`);
              setTimeout(carregar, (r.fechamentoEmSegundos + 1.5) * 1000);
            } else {
              avisoRapido(`Pedido ${r.pedidoId} criado. A solicitação aparece em instantes.`);
            }
            setTimeout(carregar, 1500);
            return true;
          } catch (erro) {
            const p = erro.problema || {};
            const detalhes = (p.erros || []).map((e) => `<li>${escapar(e.campo.replace('body.', ''))}: ${escapar(e.mensagem)}</li>`).join('');
            janela.querySelector('#erro-modal').innerHTML = erroHtml(erro) + (detalhes ? `<ul class="suave">${detalhes}</ul>` : '');
            return false;
          }
        },
      }],
    });
  }
  const STATUS = {
    ABERTA: ['Aguardando cotações', 'azul'],
    COTADA: ['Escolha o frete', 'verde'],
    SEM_COTACAO: ['Sem cotação ainda', 'ambar'],
    SELECIONADA: ['Frete escolhido', 'cinza'],
    INDISPONIVEL: ['Indisponível; nova cotação aberta', 'vermelho'],
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
      <td><strong>${escapar(s.pedido_id)}</strong>${s.rodada > 1 ? ` <span class="suave">· ${Number(s.rodada)}ª cotação</span>` : ''}
        <br><span class="suave">aberta ${formato.curta(s.aberta_em)}</span></td>
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
          ${filtro === 'todas' ? `<br>As solicitações chegam do grupo de Pedidos. ${comPedidosFalso
            ? 'No ambiente de desenvolvimento, use o botão <strong>Novo pedido de teste</strong> (administrador).' : ''}` : ''}</div>`;
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
      const admin = Portal.sessao().usuario.perfil === 'admin';
      document.getElementById('conteudo').innerHTML = `
        <div class="cabecalho"><div><h1>Solicitações de frete</h1>
          <p>Cada pedido abre uma solicitação. Compare as cotações das transportadoras e escolha o frete.</p></div>
          ${admin ? '<button type="button" class="botao primario" id="novo-pedido" hidden>+ Novo pedido de teste</button>' : ''}</div>
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
      if (admin) {
        // O botão só aparece se o pedidos-falso (desenvolvimento) responde. Com o grupo de Pedidos
        // real integrado, ele não existe e o botão some (D28).
        const botao = document.getElementById('novo-pedido');
        botao.addEventListener('click', novoPedido);
        api('/api/v1/pedidos-falso/cidades').then((lista) => { cidades = lista; comPedidosFalso = true; botao.hidden = false; })
          .catch(() => { /* sem pedidos-falso: sem botão */ });
      }
      carregar();
      setInterval(carregar, 5000);
    },
  });
})();
