/*
 * Rastreamento da entrega (etapa 3), no layout do mockup do grupo de UX
 * (portal_b2b_07_rastreamento.png).
 *
 * A tela consulta a API a cada 5 s, ou 2 s com o relógio acelerado (decisão D10). O serviço de
 * transportadoras publica uma posição a cada 30 min da hora do módulo; entre uma leitura e outra,
 * o caminhão anda aqui, a cada segundo, pela mesma conta do serviço (linha reta no tempo, da
 * última leitura até a previsão de chegada). Assim ele desliza no mapa em vez de pular.
 */
(() => {
  const { api, escapar, erroHtml, formato, pilulaStatus, icone, STATUS_ENTREGA } = Portal;
  const entregaId = new URLSearchParams(location.search).get('id');
  const mapa = { leaflet: null, percorrida: null, restante: null, caminhao: null, origem: null, destino: null, ajustado: false };
  // Última leitura do serviço e o progresso mostrado (que nunca volta).
  const leitura = { status: null, progresso: 0, em: null, chegada: null, rota: [], temRota: false, posicao: null, placa: '', mostrado: 0 };

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
          <button type="button" class="botao secundario" id="reportar" hidden>${icone('alerta')} Reportar ocorrência</button>
        </div>
      </div>
      <div id="mensagem"></div>
      <section class="cartao resumo" id="resumo" aria-live="polite"></section>
      <div class="grade-rastreio">
        <section class="cartao mapa-cartao" aria-label="Mapa da entrega">
          <div id="mapa"></div>
          <div class="selo-simulado">Dados simulados · sem GPS real</div>
          <button type="button" class="botao botao-mapa" id="atualizar-posicao" hidden>${icone('atualizar')} <span>Atualizar localização</span></button>
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
  const RAIO_ANEL = 27;
  const VOLTA_ANEL = 2 * Math.PI * RAIO_ANEL;
  // 100% só com a entrega confirmada. Antes disso, a porcentagem é arredondada para baixo e fica
  // em no máximo 99%: com o arredondamento comum, o caminhão a 99,5% do caminho já mostrava 100%.
  function porcentagemDoAnel(progresso) {
    if (leitura.status === 'ENTREGUE') return 1;
    return Math.min(0.99, Math.floor(progresso * 100) / 100);
  }

  function anel(progresso) {
    const p = porcentagemDoAnel(progresso);
    return `<div class="anel" id="anel" role="img" aria-label="Progresso ${formato.porcentagem(p)}">
      <svg viewBox="0 0 64 64"><circle class="trilho" cx="32" cy="32" r="${RAIO_ANEL}"/>
      <circle class="valor" cx="32" cy="32" r="${RAIO_ANEL}" stroke-dasharray="${VOLTA_ANEL}" stroke-dashoffset="${VOLTA_ANEL * (1 - p)}"/></svg>
      <span>${formato.porcentagem(p)}</span></div>`;
  }

  function atualizarAnel(progresso) {
    const elemento = document.getElementById('anel');
    if (!elemento) return;
    const p = porcentagemDoAnel(progresso);
    elemento.querySelector('.valor').setAttribute('stroke-dashoffset', VOLTA_ANEL * (1 - p));
    elemento.querySelector('span').textContent = formato.porcentagem(p);
    elemento.setAttribute('aria-label', `Progresso ${formato.porcentagem(p)}`);
  }

  // "Em 2 dias", "Em 3 h"... Passada a previsão sem a entrega confirmada (o serviço confirma no
  // próximo passo da viagem), mostra "Chegando ao destino" em vez de "Há 22 min".
  function previsaoRelativa(chegada, agoraIso) {
    if (leitura.status === 'EM_TRANSITO' && new Date(chegada) <= new Date(agoraIso)) return 'Chegando ao destino';
    return formato.relativo(chegada, agoraIso);
  }

  function etapas(eventos) {
    const marcos = ['VIAGEM_ALOCADA', 'COLETA_REALIZADA', 'POSICAO', 'PARADA', 'ENTREGA_REALIZADA'];
    return marcos.filter((m) => eventos.some((ev) => ev.tipo === m)).length;
  }

  function resumo(e, r) {
    const s = STATUS_ENTREGA[e.status] || { texto: e.status };
    const agora = Portal.relogio.agora();
    let previsao = `<strong>${formato.curta(e.previsao_chegada)}</strong><div class="sub" id="previsao-relativa">${
      previsaoRelativa(e.previsao_chegada, agora ? agora.toISOString() : r.horaDoModulo)}</div>`;
    if (e.status === 'ENTREGUE') {
      previsao = `<strong>${formato.curta(e.entregue_em)}</strong><div class="sub">${e.no_prazo
        ? 'Entregue no prazo' : `Entregue com ${Math.round(e.atraso_horas)} h de atraso`}</div>`;
    }
    document.getElementById('resumo').innerHTML = `
      <div><span class="icone-grande">${icone('caixa')}</span><div><small>Status da entrega</small>${pilulaStatus(e.status)}</div></div>
      <div>${anel(leitura.mostrado)}<div><small>Progresso</small><strong style="font-size:15px">${etapas(r.eventos)} de 5 etapas</strong>
        <div class="sub">${escapar(s.texto)}</div></div></div>
      <div><span class="icone-grande">${icone('calendario')}</span><div><small>${e.status === 'ENTREGUE' ? 'Chegada' : 'Previsão de chegada'}</small>${previsao}</div></div>
      <div><span class="icone-grande">${icone('predio')}</span><div><small>Transportadora</small>
        <strong title="${escapar(e.transportadora_nome)}">${escapar(e.transportadora_nome || e.transportadora_id)}</strong>
        <div class="sub">${formato.moeda(e.preco_frete)} · ${e.prazo_dias} dias úteis</div></div></div>
      <div><span class="icone-grande">${icone('caminhao')}</span><div><small>Veículo</small>
        <strong>${escapar(e.veiculo_placa || 'A definir')}</strong><div class="sub">${formato.veiculo(e.veiculo_tipo)}</div></div></div>`;
  }

  // Tipos de ocorrência da API-15 (os mesmos do mockup do grupo de UX).
  const TIPOS_OCORRENCIA = { ATRASO: 'Atraso', AVARIA: 'Avaria na carga', DESVIO_ROTA: 'Desvio de rota', OUTRO: 'Outro' };

  // ------------------------------------------------------------------ linha do tempo
  function linhaDoTempo(e, r) {
    // Ocorrências reportadas por comprador ou fornecedor entram na linha do tempo, na ordem do horário.
    const ocorrencias = (r.ocorrencias || []).map((o) => ({
      tipo: 'OCORRENCIA', ocorrido_em: o.ocorrida_em,
      descricao: `${o.tipo && o.tipo !== 'OUTRO' ? `${TIPOS_OCORRENCIA[o.tipo] || o.tipo} · ` : ''}Reportada pelo ${o.autor_papel} (protocolo ${protocolo(o.id)}): ${o.descricao}`,
    }));
    // Das posições, só a última entra ("Carga em trânsito" com a hora da leitura mais recente).
    const eventos = [...r.eventos.filter((ev, i, todos) => ev.tipo !== 'POSICAO' || todos.findLastIndex((x) => x.tipo === 'POSICAO') === i),
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

    // Telefone e CNH do motorista dependem do perfil (a API manda null para quem não pode ver):
    // o comprador não vê nenhum dos dois, o fornecedor vê o telefone e o admin vê os dois.
    const perfil = Portal.sessao().usuario.perfil;
    document.getElementById('dados-motorista').innerHTML = e.motorista_nome ? [
      par('Motorista', escapar(e.motorista_nome)),
      ['fornecedor', 'admin'].includes(perfil) ? par('Telefone', escapar(e.motorista_telefone || '—')) : '',
      perfil === 'admin' ? par('CNH', escapar(e.motorista_cnh_mascarada || '—')) : '',
      '<hr>',
      par('Veículo', escapar(e.veiculo_placa)),
      par('Tipo', formato.veiculo(e.veiculo_tipo)),
      par('Transportadora', escapar(e.transportadora_nome)),
      par('Contato da transportadora', escapar(e.transportadora_telefone || '—')),
      // Como no mockup do UX (UX-RAS-06): o cartão deixa claro que as pessoas e os contatos não são reais.
      '<dd class="nota-ficticia">Dados fictícios, só para demonstração.</dd>',
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
  const protocolo = (id) => `OC-${String(id || '').replace(/-/g, '').slice(0, 8).toUpperCase()}`;

  function reportarOcorrencia() {
    Portal.modal({
      titulo: 'Reportar ocorrência',
      conteudo: `<p class="suave" style="margin-top:0">A outra parte do pedido é avisada.</p>
        <div class="campo" id="c-tipo-ocorrencia"><label for="tipo-ocorrencia">Tipo de ocorrência <span class="obrigatorio">*</span></label>
        <select id="tipo-ocorrencia" required><option value="">Selecione…</option>
          ${Object.entries(TIPOS_OCORRENCIA).map(([valor, nome]) => `<option value="${valor}">${nome}</option>`).join('')}</select></div>
        <div class="campo" id="c-ocorrencia"><label for="ocorrencia">O que aconteceu? <span class="obrigatorio">*</span></label>
        <textarea id="ocorrencia" maxlength="500" placeholder="Até 500 caracteres"></textarea></div><div id="erro-modal"></div>`,
      botoes: [{ texto: 'Cancelar' }, {
        texto: 'Enviar', classe: 'primario', async acao(janela) {
          const tipo = janela.querySelector('#tipo-ocorrencia').value;
          const descricao = janela.querySelector('#ocorrencia').value.trim();
          const erro = janela.querySelector('#erro-modal');
          if (!tipo || !descricao) {
            erro.innerHTML = `<div class="aviso erro" role="alert">${!tipo ? 'Selecione o tipo de ocorrência.' : 'Descreva o que aconteceu.'}</div>`;
            janela.querySelector(!tipo ? '#tipo-ocorrencia' : '#ocorrencia').focus();
            return false;
          }
          try {
            const ocorrencia = await api(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}/ocorrencias`, {
              metodo: 'POST', corpo: { tipo, descricao },
            });
            // Protocolo para a pessoa citar depois (UX-RAS-08): os 8 primeiros caracteres do id da ocorrência.
            Portal.avisoRapido(`Ocorrência registrada. Protocolo ${protocolo(ocorrencia.id)}.`);
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

  // Guarda a leitura do serviço. Em trânsito, o progresso mostrado nunca volta: quando o atraso
  // aparece, a previsão de chegada aumenta e a conta daqui pode ter passado um pouco da do serviço;
  // o caminhão espera o serviço alcançá-lo, em vez de recuar no mapa.
  function registrarLeitura(e, r) {
    const origem = [r.origem.lat, r.origem.lon];
    const destino = [r.destino.lat, r.destino.lon];
    Object.assign(leitura, {
      status: e.status, progresso: Number(r.progresso), em: r.posicaoEm, chegada: r.previsaoChegada || e.previsao_chegada,
      rota: r.rota.length ? r.rota : [origem, destino], temRota: r.rota.length > 0,
      posicao: r.posicao ? [r.posicao.lat, r.posicao.lon] : null, placa: e.veiculo_placa || '',
    });
    const agora = Portal.relogio.agora();
    leitura.mostrado = e.status === 'EM_TRANSITO'
      ? Math.max(leitura.mostrado, leitura.progresso, agora ? progressoEstimado(agora) : 0) : leitura.progresso;
  }

  // A mesma conta do serviço (simulacao.progresso): da última leitura até a chegada, em linha reta no tempo.
  function progressoEstimado(agora) {
    const { progresso: p0, em, chegada } = leitura;
    if (leitura.status !== 'EM_TRANSITO' || !em || !chegada) return p0;
    const t0 = new Date(em).getTime();
    const t1 = new Date(chegada).getTime();
    const t = agora.getTime();
    if (t1 <= t0 || t <= t0) return p0;
    // Para antes do destino: quem confirma a entrega é o serviço.
    return Math.min(0.995, p0 + ((1 - p0) * (t - t0)) / (t1 - t0));
  }

  function atualizarMapa(e, r) {
    if (typeof L === 'undefined') { mapaEmTexto(e, r); return; }
    const origem = [r.origem.lat, r.origem.lon];
    const destino = [r.destino.lat, r.destino.lon];

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

    desenharPosicao(Portal.relogio.agora() || new Date(r.horaDoModulo));

    if (!mapa.ajustado) {
      mapa.leaflet.fitBounds(L.latLngBounds([origem, destino, ...leitura.rota]), { padding: [70, 70] });
      mapa.ajustado = true;
    }
  }

  // Chamado a cada leitura e a cada segundo do relógio (evento "portal:segundo").
  function desenharPosicao(agora) {
    if (!mapa.leaflet || !leitura.status) return;
    const emTransito = leitura.status === 'EM_TRANSITO';
    if (emTransito) leitura.mostrado = Math.max(leitura.mostrado, progressoEstimado(agora));
    const { percorrida, restante, ponto } = dividirRota(leitura.rota, leitura.mostrado);
    const temViagem = leitura.temRota && !['CANCELADA', 'RECUSADA'].includes(leitura.status);
    mapa.percorrida.setLatLngs(temViagem ? percorrida : []);
    mapa.restante.setLatLngs(temViagem ? restante : leitura.rota);

    const posicao = emTransito || !leitura.posicao ? ponto : leitura.posicao;
    const legenda = emTransito ? `Posição às ${formato.hora(agora.toISOString())} (hora do módulo)`
      : leitura.status === 'AGUARDANDO_COLETA' ? 'Aguardando a coleta' : '';
    const textoCaminhao = `Veículo ${escapar(leitura.placa)}<small>${legenda}</small>`;
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
  }

  // A cada segundo: caminhão, anel de progresso e "Em N dias" acompanham o relógio do topo.
  function aCadaSegundo(ev) {
    if (!leitura.status) return;
    const { agora } = ev.detail;
    desenharPosicao(agora);
    atualizarAnel(leitura.mostrado);
    const relativa = document.getElementById('previsao-relativa');
    if (relativa && leitura.chegada && leitura.status !== 'ENTREGUE') {
      relativa.textContent = previsaoRelativa(leitura.chegada, agora.toISOString());
    }
  }

  // ------------------------------------------------------------------ ciclo de atualização
  // A tela já atualiza sozinha a cada 5 s (2 s acelerado). O botão força uma atualização na hora e centraliza o
  // caminhão, com dois limites para não sobrecarregar o serviço: uma consulta por vez
  // (`emAndamento`) e uma espera de ESPERA_BOTAO_S segundos entre um clique e o próximo.
  const ESPERA_BOTAO_S = 5;
  let emAndamento = null;

  function carregar() {
    if (!emAndamento) emAndamento = buscar().finally(() => { emAndamento = null; });
    return emAndamento;
  }

  async function atualizarAgora() {
    const botao = document.getElementById('atualizar-posicao');
    const texto = botao.querySelector('span');
    botao.disabled = true;
    texto.textContent = 'Atualizando…';
    await carregar();
    if (mapa.leaflet && mapa.caminhao) mapa.leaflet.panTo(mapa.caminhao.getLatLng(), { animate: true });
    let restante = ESPERA_BOTAO_S;
    const contar = () => {
      if (restante <= 0) { botao.disabled = false; texto.textContent = 'Atualizar localização'; return; }
      texto.textContent = `Atualizado · de novo em ${restante} s`;
      restante -= 1;
      setTimeout(contar, 1000);
    };
    contar();
  }

  async function buscar() {
    try {
      const [e, r] = await Promise.all([
        api(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}`),
        api(`/api/v1/logistica/entregas/${encodeURIComponent(entregaId)}/rastreio`),
      ]);
      document.getElementById('mensagem').innerHTML = '';
      document.getElementById('titulo').textContent = `Entrega #${e.pedido_id}`;
      document.title = `Entrega ${e.pedido_id} · Portal B2B`;
      registrarLeitura(e, r);
      resumo(e, r);
      linhaDoTempo(e, r);
      detalhes(e);
      const podeReportar = ['comprador', 'fornecedor'].includes(Portal.sessao().usuario.perfil)
        && !['CANCELADA', 'RECUSADA'].includes(e.status);
      document.getElementById('reportar').hidden = !podeReportar;
      try { atualizarMapa(e, r); } catch (erroMapa) { console.error(erroMapa); mapaEmTexto(e, r); }
      // O botão só faz sentido com o caminhão na estrada.
      document.getElementById('atualizar-posicao').hidden = !['AGUARDANDO_COLETA', 'EM_TRANSITO'].includes(e.status);
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
      document.getElementById('atualizar-posicao').addEventListener('click', atualizarAgora);
      carregar();
      Portal.repetir(carregar);  // 5 s, ou 2 s com o relógio acelerado
      document.addEventListener('portal:segundo', aCadaSegundo);
    },
  });
})();
