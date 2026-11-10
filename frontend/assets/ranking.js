/* Ranking de desempenho das transportadoras (decisão D6). Ordenado pela pontualidade. */
(() => {
  const { api, escapar, erroHtml, formato, icone } = Portal;
  let tipo = '';

  function linha(t) {
    const pct = t.pct_no_prazo;
    return `<tr>
      <td><span class="posicao ${t.posicao === 1 && pct != null ? 'ouro' : ''}">${t.posicao}</span></td>
      <td><strong>${escapar(t.nome)}</strong><br><span class="chips">
        ${t.simulada ? '<span class="chip">simulada</span>' : '<span class="chip ambar">cota digitando</span>'}
        ${t.tipos_carga.map((c) => `<span class="chip">${formato.tipoCarga(c)}</span>`).join('')}</span></td>
      <td>${t.entregas}</td>
      <td>${pct == null ? '<span class="suave">sem entregas</span>'
        : `<span class="pontualidade"><span class="barra"><span style="width:${Math.round(pct * 100)}%"></span></span><b>${formato.porcentagem(pct)}</b></span>`}</td>
      <td class="opcional">${t.atraso_medio_horas == null ? '—' : `${Number(t.atraso_medio_horas).toLocaleString('pt-BR')} h`}</td>
      <td class="opcional">${formato.precoTkm(t.preco_medio_t_km)}</td>
      <td>${t.vezes_escolhida} <span class="suave">de ${t.cotacoes} cotações</span></td>
    </tr>`;
  }

  async function carregar() {
    const lista = document.getElementById('lista');
    try {
      const r = await api(`/api/v1/transportadoras/ranking?size=100${tipo ? `&tipoCarga=${tipo}` : ''}`);
      document.getElementById('mensagem').innerHTML = '';
      lista.className = '';
      lista.innerHTML = r.items.length ? `<table class="tabela"><thead><tr><th>#</th><th>Transportadora</th><th>Entregas</th>
        <th>No prazo</th><th class="opcional">Atraso médio</th><th class="opcional">Preço médio</th><th>Escolhida</th></tr></thead>
        <tbody>${r.items.map(linha).join('')}</tbody></table>` : '<div class="vazio-grande">Nenhuma transportadora.</div>';
    } catch (erro) {
      document.getElementById('mensagem').innerHTML = erroHtml(erro);
    }
  }

  Portal.iniciar({
    ativo: 'transportadoras',
    aoEntrar() {
      document.getElementById('conteudo').innerHTML = `
        <div class="cabecalho"><div><h1>Ranking de transportadoras</h1>
          <p>Quem entrega no prazo, quanto atrasa e quanto cobra. Os números vêm das entregas feitas no portal.</p></div></div>
        <div class="filtros" id="filtros">
          <button type="button" data-tipo="" class="ativo">Todas as cargas</button>
          <button type="button" data-tipo="GRANEL">Granel</button><button type="button" data-tipo="CARGA_SECA">Carga seca</button>
          <button type="button" data-tipo="REFRIGERADO">Refrigerada</button><button type="button" data-tipo="PERIGOSO">Perigosa</button>
        </div>
        <div id="mensagem"></div>
        <section class="cartao"><div id="lista" class="carregando">Carregando…</div></section>
        <p class="suave">${icone('relogio')} "No prazo" = entregue até 23h59 (Brasília) da data prometida na cotação.
          Preço médio = valor do frete ÷ (toneladas × km), para comparar cargas e rotas de tamanhos diferentes.</p>`;
      document.getElementById('filtros').addEventListener('click', (ev) => {
        const botao = ev.target.closest('button[data-tipo]');
        if (!botao) return;
        tipo = botao.dataset.tipo;
        document.querySelectorAll('#filtros button').forEach((b) => b.classList.toggle('ativo', b === botao));
        carregar();
      });
      carregar();
      setInterval(carregar, 10000);
    },
  });
})();
