/* Lista de entregas: atualiza a cada 5 s (decisão D10). */
(() => {
  const { api, escapar, erroHtml, formato, pilulaStatus } = Portal;
  const GRUPOS = {
    todas: null,
    andamento: ['AGUARDANDO_ALOCACAO', 'AGUARDANDO_COLETA', 'EM_TRANSITO'],
    entregues: ['ENTREGUE'],
    canceladas: ['CANCELADA'],
  };
  let filtro = 'todas';

  function linha(e) {
    const rota = `${escapar(e.origem_cidade)} - ${escapar(e.origem_uf)} → ${escapar(e.destino_cidade)} - ${escapar(e.destino_uf)}`;
    const quando = e.status === 'ENTREGUE'
      ? `<span class="suave">Entregue</span><br>${formato.curta(e.entregue_em)}
         ${e.no_prazo === false ? `<br><span class="pilula ambar">${Math.round(e.atraso_horas)} h de atraso</span>` : ''}`
      : e.status === 'CANCELADA' || e.status === 'RECUSADA' || !e.previsao_chegada
        ? '<span class="tracinho">—</span>'
        : `<span class="suave">Previsão</span><br>${formato.curta(e.previsao_chegada)}`;
    const encerrada = e.status === 'CANCELADA' || e.status === 'RECUSADA';
    // 100% só com a entrega confirmada; antes, arredonda para baixo e fica em no máximo 99%.
    const pct = e.status === 'ENTREGUE' ? 100 : Math.min(99, Math.floor(Number(e.progresso) * 100));
    return `<tr data-id="${escapar(e.id)}" tabindex="0">
      <td><strong>${escapar(e.pedido_id)}</strong>${e.tentativa > 1 ? `<br><span class="suave">tentativa ${e.tentativa}</span>` : ''}</td>
      <td><span class="rota">${rota}</span><br><span class="suave">${escapar(e.produto_nome)} · ${formato.toneladas(e.peso_kg)}</span></td>
      <td class="opcional">${escapar(e.transportadora_nome || e.transportadora_id)}<br><span class="suave">${escapar(e.veiculo_placa || '')}</span></td>
      <td>${pilulaStatus(e.status)}</td>
      <td class="opcional">${encerrada ? '<span class="tracinho">—</span>' : `<div class="barra" role="progressbar"
          aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100" aria-label="Progresso">
          <span style="width:${pct}%"></span></div>
        <span class="suave">${pct}%</span>`}</td>
      <td>${quando}</td>
      <td class="seta"><span class="link-acao">${encerrada ? 'Ver ›' : 'Acompanhar ›'}</span></td>
    </tr>`;
  }

  async function carregar() {
    const lista = document.getElementById('lista');
    try {
      const r = await api('/api/v1/logistica/entregas?size=100');
      const grupo = GRUPOS[filtro];
      const itens = grupo ? r.items.filter((e) => grupo.includes(e.status)) : r.items;
      document.querySelectorAll('#filtros button[data-filtro]').forEach((b) => {
        const g = GRUPOS[b.dataset.filtro];
        const n = g ? r.items.filter((e) => g.includes(e.status)).length : r.items.length;
        let contagem = b.querySelector('.contagem');
        if (!contagem) { contagem = document.createElement('span'); contagem.className = 'contagem'; b.appendChild(contagem); }
        contagem.textContent = n;
      });
      document.getElementById('mensagem').innerHTML = '';
      lista.className = '';
      if (!itens.length) {
        lista.innerHTML = `<div class="vazio-grande">Nenhuma entrega ${filtro === 'todas' ? 'ainda' : 'neste filtro'}.
          ${filtro === 'todas' ? '<br>A entrega aparece aqui assim que o frete de um pedido é escolhido, na tela <a href="solicitacoes.html">Solicitações de frete</a>.' : ''}</div>`;
        return;
      }
      lista.innerHTML = `<table class="tabela">
        <thead><tr><th>Pedido</th><th>Rota e carga</th><th class="opcional">Transportadora</th><th>Status</th>
          <th class="opcional">Progresso</th><th>Chegada</th><th><span class="sr-only">Ação</span></th></tr></thead>
        <tbody>${itens.map(linha).join('')}</tbody></table>`;
      lista.querySelectorAll('tbody tr').forEach((tr) => {
        const abrir = () => { location.href = `entrega.html?id=${encodeURIComponent(tr.dataset.id)}`; };
        tr.addEventListener('click', abrir);
        tr.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') abrir(); });
      });
    } catch (erro) {
      lista.className = '';
      lista.innerHTML = '';
      const msg = erro.status === 403
        ? 'O seu perfil não acompanha entregas. Entre como comprador, fornecedor ou administrador pelo menu do usuário.'
        : '';
      document.getElementById('mensagem').innerHTML = erroHtml(erro) + (msg ? `<div class="aviso info">${msg}</div>` : '');
    }
  }

  Portal.iniciar({
    ativo: 'entregas',
    perfis: ['comprador', 'fornecedor', 'admin'],
    aoEntrar() {
      document.getElementById('filtros').addEventListener('click', (ev) => {
        const botao = ev.target.closest('button[data-filtro]');
        if (!botao) return;
        filtro = botao.dataset.filtro;
        document.querySelectorAll('#filtros button').forEach((b) => b.classList.toggle('ativo', b === botao));
        carregar();
      });
      carregar();
      Portal.repetir(carregar);
    },
  });
})();
