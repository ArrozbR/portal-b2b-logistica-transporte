/*
 * Rastreamento da entrega (etapa 3), no layout do mockup do grupo de UX
 * (portal_b2b_07_rastreamento.png).
 *
 * A tela consulta a API a cada 5 s (decisão D10). A posição do caminhão é
 * simulada pelo serviço de transportadoras e muda a cada 30 s; as datas estão
 * na hora do módulo, que o administrador pode acelerar.
 */
(() => {
  const { api, escapar, erroHtml, formato, pilulaStatus, icone, STATUS_ENTREGA } = Portal;
  const entregaId = new URLSearchParams(location.search).get('id');
  const mapa = { leaflet: null, percorrida: null, restante: null, caminhao: null, origem: null, destino: null, ajustado: false };

  const TITULOS = {
    VIAGEM_ALOCADA: 'Motorista escalado',
    COLETA_REALIZADA: 'Coleta realizada',
    POSICAO: 'Carga em trânsito',
    PARADA: 'Parada operacional',
    PREVISAO_ATUALIZADA: 'Previsão atualizada',
    OCORRENCIA: 'Ocorrência registrada',
    ENTREGA_REALIZADA: 'Entrega confirmada',
  };

  // ------------------------------------------------------------------ estrutura
  function esqueleto() {
    document.getElementById('conteudo').innerHTML = `
      <a class="voltar" href="index.html">${icone('seta')} Voltar para entregas</a>
      <div class="cabecalho">
        <div><h1 id="titulo">Entrega</h1><p>Acompanhe o transporte e os eventos da entrega em tempo real.</p></div>
        <div class="acoes">
          <button type="button" class="botao primario" id="reportar" hidden>${icone('alerta')} Reportar ocorrência</button>
        </div>
      </div>
      <div id="mensagem"></div>
      <section class="cartao resumo" id="resumo" aria-live="polite"></section>
      <div class="grade-rastreio">
        <section class="cartao mapa-cartao" aria-label="Mapa da entrega">
          <div id="mapa"></div>
          <div class="selo-simulado">Dados simulados · sem GPS real</div>
          <div class="legenda" id="legenda">
            <span><i></i>Rota percorrida</span><span><i class="restante"></i>Rota restante</span>
            <span><i class="ponto"></i>Posição atual</span><span><i class="destino"></i>Destino</span>
          </div>
        </section>
        <section class="cartao"><h2>${icone('relogio')} Linha do tempo</h2><ol class="linha-tempo" id="linha-tempo"></ol></section>
      </div>
      <div class="grade-detalhes">
        <section class="cartao"><h2>${icone('caixa')} Dados da carga</h2><div class="corpo"><dl class="dados" id="dados-carga"></dl></div></section>
        <section class="cartao"><h2>${icone('usuario')} Motorista e veículo</h2><div class="corpo"><dl class="dados" id="dados-motorista"></dl></div></section>
        <section class="cartao"><h2>${icone('arquivo')} Documentos</h2><div class="corpo"><ul class="documentos" id="documentos"></ul></div></section>
      </div>`;
  }

  const par = (rotulo, valor) => `<dt>${escapar(rotulo)}</dt><dd>${valor}</dd>`;

  // ------------------------------------------------------------------ faixa de resumo
  function anel(progresso) {
    const raio = 27;
    const volta = 2 * Math.PI * raio;
    return `<div class="anel" role="img" aria-label="Progresso ${formato.porcentagem(progresso)}">
      <svg viewBox="0 0 64 64"><circle class="trilho" cx="32" cy="32" r="${raio}"/>
      <circle class="valor" cx="32" cy="32" r="${raio}" stroke-dasharray="${volta}" stroke-dashoffset="${volta * (1 - progresso)}"/></svg>
      <span>${formato.porcentagem(progresso)}</span></div>`;
  }

  function etapas(eventos) {
    const marcos = ['VIAGEM_ALOCADA', 'COLETA_REALIZADA', 'POSICAO', 'PARADA', 'ENTREGA_REALIZADA'];
    return marcos.filter((m) => eventos.some((ev) => ev.tipo === m)).length;
  }

  function resumo(e, r) {
    const s = STATUS_ENTREGA[e.status] || { texto: e.status };
    let previsao = `<strong>${formato.curta(e.previsao_chegada)}</strong><div class="sub">${formato.relativo(e.previsao_chegada, r.horaDoModulo)}</div>`;
    if (e.status === 'ENTREGUE') {
      previsao = `<strong>${formato.curta(e.entregue_em)}</strong><div class="sub">${e.no_prazo
        ? 'Entregue no prazo' : `Entregue com ${Math.round(e.atraso_horas)} h de atraso`}</div>`;
    }
    document.getElementById('resumo').innerHTML = `
      <div><span class="icone-grande">${icone('caixa')}</span><div><small>Status da entrega</small>${pilulaStatus(e.status)}</div></div>
      <div>${anel(Number(r.progresso))}<div><small>Progresso</small><strong style="font-size:15px">${etapas(r.eventos)} de 5 etapas</strong>
        <div class="sub">${escapar(s.texto)}</div></div></div>
      <div><span class="icone-grande">${icone('calendario')}</span><div><small>${e.status === 'ENTREGUE' ? 'Chegada' : 'Previsão de chegada'}</small>${previsao}</div></div>
      <div><span class="icone-grande">${icone('predio')}</span><div><small>Transportadora</small>
        <strong title="${escapar(e.transportadora_nome)}">${escapar(e.transportadora_nome || e.transportadora_id)}</strong>
        <div class="sub">${formato.moeda(e.preco_frete)} · ${e.prazo_dias} dias úteis</div></div></div>
      <div><span class="icone-grande">${icone('caminhao')}</span><div><small>Veículo</small>
        <strong>${escapar(e.veiculo_placa || 'A definir')}</strong><div class="sub">${formato.veiculo(e.veiculo_tipo)}</div></div></div>`;
  }

  // ------------------------------------------------------------------ linha do tempo
  function linhaDoTempo(e, r) {
    // Ocorrências reportadas por comprador ou fornecedor entram na linha do tempo, na ordem do horário.
    const ocorrencias = (r.ocorrencias || []).map((o) => ({
      tipo: 'OCORRENCIA', ocorrido_em: o.ocorrida_em,
      descricao: `Reportada pelo ${o.autor_papel}: ${o.descricao}`,
    }));
    const eventos = [...r.eventos.filter((ev, i, todos) => ev.tipo !== 'POSICAO' || todos.findIndex((x) => x.tipo === 'POSICAO') === i),
      ...ocorrencias].sort((a, b) => new Date(a.ocorrido_em) - new Date(b.ocorrido_em));
    const encerrada = ['ENTREGUE', 'CANCELADA', 'RECUSADA'].includes(e.status);
    const itens = eventos.map((ev, i) => {
      const ultimo = i === eventos.length - 1 && !encerrada;
      const classe = ev.tipo === 'PREVISAO_ATUALIZADA' || ev.tipo === 'OCORRENCIA' ? 'alerta' : ultimo ? 'atual' : '';
      const marca = classe === 'alerta' ? icone('alerta') : ultimo ? icone('caminhao') : icone('check');
      return `<li class="${classe}"><span class="marca">${marca}</span>
        <div><strong>${escapar(TITULOS[ev.tipo] || ev.tipo)}</strong><p>${escapar(ev.descricao)}</p></div>
        <time>${formato.diaMes(ev.ocorrido_em)}<br>${formato.hora(ev.ocorrido_em)}</time></li>`;
    });
    const pendente = (titulo, texto, iso) => `<li class="pendente"><span class="marca">${icone('relogio')}</span>
      <div><strong>${titulo}</strong><p>${texto}</p></div><time>${iso ? `${formato.diaMes(iso)}<br>${formato.hora(iso)}` : ''}</time></li>`;
    if (!encerrada) {
      if (!r.eventos.some((ev) => ev.tipo === 'COLETA_REALIZADA')) {
        itens.push(pendente('Coleta', e.coleta_prevista ? 'Coleta agendada no armazém do fornecedor.'
          : 'Aguardando a transportadora escalar motorista e veículo.', e.coleta_prevista));
      }
      itens.push(pendente('Entrega confirmada', `Aguardando confirmação de entrega em ${escapar(r.destino.cidade)} - ${escapar(r.destino.uf)}.`,
        e.previsao_chegada));
    } else if (e.status !== 'ENTREGUE') {
      itens.push(`<li class="alerta"><span class="marca">${icone('alerta')}</span><div><strong>${escapar(STATUS_ENTREGA[e.status].texto)}</strong>
        <p>${e.status === 'RECUSADA' ? 'A transportadora não tinha frota livre; o frete passou para a próxima cotação.'
          : 'O pedido foi cancelado.'}</p></div><time></time></li>`);
    }
    document.getElementById('linha-tempo').innerHTML = itens.join('');
  }

  // ------------------------------------------------------------------ cartões de detalhe
  function detalhes(e) {
    const coleta = e.coletada_em || e.coleta_prevista;
    document.getElementById('dados-carga').innerHTML = [
      par('Produto', escapar(e.produto_nome)),
      par('Quantidade', formato.peso(e.peso_kg)),
      par('Tipo', formato.tipoCarga(e.tipo_carga)),
      par('Valor da carga', formato.moeda(e.valor_carga)),
      par('Origem', `${escapar(e.origem_cidade)} - ${escapar(e.origem_uf)}`),
      par('Destino', `${escapar(e.destino_cidade)} - ${escapar(e.destino_uf)}`),
      par('Distância', `${Number(e.distancia_km).toLocaleString('pt-BR')} km`),
      par(e.coletada_em ? 'Data de coleta' : 'Coleta prevista', formato.completa(coleta)),
      par('Prazo prometido', formato.data(e.prazo_prometido)),
    ].join('');

    document.getElementById('dados-motorista').innerHTML = e.motorista_nome ? [
      par('Motorista', escapar(e.motorista_nome)),
      par('Telefone', escapar(e.motorista_telefone || '—')),
      par('CNH', escapar(e.motorista_cnh_mascarada || '—')),
      '<hr>',
      par('Veículo', escapar(e.veiculo_placa)),
      par('Tipo', formato.veiculo(e.veiculo_tipo)),
      par('Transportadora', escapar(e.transportadora_nome)),
      par('Contato da transportadora', escapar(e.transportadora_telefone || '—')),
    ].join('') : `<dd style="grid-column:1/-1;color:var(--texto-suave)">${e.status === 'RECUSADA'
      ? 'A transportadora recusou a viagem por falta de frota livre.'
      : 'A transportadora ainda está escalando o motorista e o veículo.'}</dd>`;

    const docs = [['cte', 'CT-e', 'Conhecimento de transporte'], ['romaneio', 'Romaneio de carga', 'Lista da carga'],
      ['nota-fiscal', 'Nota fiscal', 'Emitida pelo fornecedor'], ['comprovante-coleta', 'Comprovante de coleta', 'Após a coleta']];
    const lista = document.getElementById('documentos');
    lista.innerHTML = docs.map(([tipo, nome, sub]) => {
      const disponivel = tipo !== 'comprovante-coleta' || e.coletada_em;
      return `<li><span class="arquivo">${icone('arquivo')}</span><span><strong>${nome}</strong><small>${sub} · PDF demonstrativo, sem valor fiscal</small></span>
        <button type="button" data-documento="${tipo}" ${disponivel ? '' : 'disabled title="Disponível depois da coleta"'} aria-label="Baixar ${nome}">${icone('download')}</button></li>`;
    }).join('');
    lista.querySelectorAll('[data-documento]').forEach((b) => b.addEventListener('click', async () => {
      try {
        await Portal.baixar(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}/documentos/${b.dataset.documento}`,
          `${b.dataset.documento}-${e.pedido_id}.pdf`);
      } catch (erro) { Portal.avisoRapido(erro.message, true); }
    }));
  }

  // ------------------------------------------------------------------ ocorrência
  function reportarOcorrencia() {
    Portal.modal({
      titulo: 'Reportar ocorrência',
      conteudo: `<p class="suave" style="margin-top:0">Descreva o problema (avaria, atraso sem aviso, divergência na carga...).
        A outra parte do pedido é avisada.</p>
        <div class="campo"><label for="ocorrencia">O que aconteceu? <span class="obrigatorio">*</span></label>
        <textarea id="ocorrencia" maxlength="500" minlength="5"></textarea></div><div id="erro-modal"></div>`,
      botoes: [{ texto: 'Cancelar' }, {
        texto: 'Enviar', classe: 'primario', async acao(janela) {
          try {
            await api(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}/ocorrencias`, {
              metodo: 'POST', corpo: { descricao: janela.querySelector('#ocorrencia').value.trim() },
            });
            Portal.avisoRapido('Ocorrência registrada.');
            carregar();
            return true;
          } catch (erro) { janela.querySelector('#erro-modal').innerHTML = erroHtml(erro); return false; }
        },
      }],
    });
  }

  // ------------------------------------------------------------------ mapa
  function distanciaKm([lat1, lon1], [lat2, lon2]) {
    const rad = (g) => (g * Math.PI) / 180;
    const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(a));
  }

  function dividirRota(rota, progresso) {
    // Separa a rota em "percorrida" e "restante" no ponto que corresponde ao progresso.
    const trechos = rota.slice(1).map((p, i) => distanciaKm(rota[i], p));
    const alvo = trechos.reduce((a, b) => a + b, 0) * progresso;
    let andado = 0;
    for (let i = 0; i < trechos.length; i += 1) {
      if (andado + trechos[i] >= alvo) {
        const f = trechos[i] ? (alvo - andado) / trechos[i] : 0;
        const ponto = [rota[i][0] + (rota[i + 1][0] - rota[i][0]) * f, rota[i][1] + (rota[i + 1][1] - rota[i][1]) * f];
        return { percorrida: [...rota.slice(0, i + 1), ponto], restante: [ponto, ...rota.slice(i + 1)], ponto };
      }
      andado += trechos[i];
    }
    return { percorrida: rota, restante: [rota[rota.length - 1]], ponto: rota[rota.length - 1] };
  }

  function mapaEmTexto(e, r) {
    document.getElementById('mapa').innerHTML = `<div class="mapa-texto">
      <strong>${escapar(r.origem.cidade)} - ${escapar(r.origem.uf)} → ${escapar(r.destino.cidade)} - ${escapar(r.destino.uf)}</strong>
      <span>O mapa não pôde ser carregado. Progresso: ${formato.porcentagem(r.progresso)}.</span>
      <span>Última posição: ${r.posicao ? `${r.posicao.lat.toFixed(3)}, ${r.posicao.lon.toFixed(3)}` : '—'}
        ${r.posicaoEm ? `(${formato.completa(r.posicaoEm)})` : ''}</span></div>`;
    document.getElementById('legenda').hidden = true;
  }

  function rotuloCidade(cidade, tag, cinza) {
    return `${escapar(cidade.cidade)} - ${escapar(cidade.uf)}<br><span class="tag ${cinza ? 'cinza' : ''}">${tag}</span>`;
  }

  function atualizarMapa(e, r) {
    if (typeof L === 'undefined') { mapaEmTexto(e, r); return; }
    const origem = [r.origem.lat, r.origem.lon];
    const destino = [r.destino.lat, r.destino.lon];
    const rota = r.rota.length ? r.rota : [origem, destino];

    if (!mapa.leaflet) {
      mapa.leaflet = L.map('mapa', { zoomControl: true, attributionControl: true, scrollWheelZoom: false });
      L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; colaboradores do <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(mapa.leaflet);
      const icone = (classe) => L.divIcon({ className: '', html: `<div class="marcador-cidade ${classe}"><span class="bolinha"></span></div>`, iconSize: [24, 24], iconAnchor: [12, 12] });
      mapa.origem = L.marker(origem, { icon: icone('') }).addTo(mapa.leaflet)
        .bindTooltip(rotuloCidade(r.origem, 'Origem'), { permanent: true, direction: 'right', offset: [12, 0], className: 'rotulo' });
      mapa.destino = L.marker(destino, { icon: icone('destino') }).addTo(mapa.leaflet)
        .bindTooltip(rotuloCidade(r.destino, 'Destino', true), { permanent: true, direction: 'right', offset: [12, 0], className: 'rotulo' });
      mapa.restante = L.polyline([], { color: '#9ca3af', weight: 3, dashArray: '6 8' }).addTo(mapa.leaflet);
      mapa.percorrida = L.polyline([], { color: '#84cc16', weight: 5, lineCap: 'round' }).addTo(mapa.leaflet);
    }

    const { percorrida, restante, ponto } = dividirRota(rota, Number(r.progresso));
    const temViagem = r.rota.length > 0 && e.status !== 'CANCELADA' && e.status !== 'RECUSADA';
    mapa.percorrida.setLatLngs(temViagem ? percorrida : []);
    mapa.restante.setLatLngs(temViagem ? restante : rota);

    const posicao = r.posicao ? [r.posicao.lat, r.posicao.lon] : ponto;
    const textoCaminhao = `Veículo ${escapar(e.veiculo_placa || '')}<small>${r.posicaoEm
      ? `Atualizado ${formato.relativo(r.posicaoEm, r.horaDoModulo).toLowerCase()} (hora do módulo)` : ''}</small>`;
    if (temViagem && !mapa.caminhao) {
      mapa.caminhao = L.marker(posicao, {
        icon: L.divIcon({ className: '', html: `<div class="marcador-caminhao">${Portal.icone('caminhao', '')}</div>`, iconSize: [40, 40], iconAnchor: [20, 20] }),
        zIndexOffset: 1000,
      }).addTo(mapa.leaflet).bindTooltip(textoCaminhao, { permanent: true, direction: 'top', offset: [0, -22], className: 'rotulo' });
    } else if (mapa.caminhao) {
      if (temViagem) {
        mapa.caminhao.setLatLng(posicao);
        mapa.caminhao.setTooltipContent(textoCaminhao);
      } else {
        mapa.caminhao.remove();
        mapa.caminhao = null;
      }
    }

    if (!mapa.ajustado) {
      mapa.leaflet.fitBounds(L.latLngBounds([origem, destino, ...rota]), { padding: [70, 70] });
      mapa.ajustado = true;
    }
  }

  // ------------------------------------------------------------------ ciclo de atualização
  async function carregar() {
    try {
      const [e, r] = await Promise.all([
        api(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}`),
        api(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}/rastreio`),
      ]);
      document.getElementById('mensagem').innerHTML = '';
      document.getElementById('titulo').textContent = `Entrega #${e.pedido_id}`;
      document.title = `Entrega ${e.pedido_id} · Portal B2B`;
      resumo(e, r);
      linhaDoTempo(e, r);
      detalhes(e);
      const podeReportar = ['comprador', 'fornecedor'].includes(Portal.sessao().usuario.perfil)
        && !['CANCELADA', 'RECUSADA'].includes(e.status);
      document.getElementById('reportar').hidden = !podeReportar;
      try { atualizarMapa(e, r); } catch (erroMapa) { console.error(erroMapa); mapaEmTexto(e, r); }
    } catch (erro) {
      document.getElementById('mensagem').innerHTML = erroHtml(erro);
    }
  }

  Portal.iniciar({
    ativo: 'entregas',
    perfis: ['comprador', 'fornecedor', 'admin'],
    aoEntrar() {
      if (!entregaId) {
        document.getElementById('conteudo').innerHTML = `<a class="voltar" href="index.html">${icone('seta')} Voltar para entregas</a>
          <div class="aviso erro">Nenhuma entrega informada no endereço.</div>`;
        return;
      }
      esqueleto();
      document.getElementById('reportar').addEventListener('click', reportarOcorrencia);
      carregar();
      setInterval(carregar, 5000);
    },
  });
})();
