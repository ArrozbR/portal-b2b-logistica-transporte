/*
 * Minha frota: cadastro de motoristas e veículos da transportadora (decisão D19).
 * Telefone e CNH completos aparecem só aqui, para a própria transportadora (LGPD).
 */
(() => {
  const { api, escapar, erroHtml, formato, icone, modal, avisoRapido } = Portal;
  let transportadora = null;
  const itens = { motoristas: [], veiculos: [] };  // última lista carregada (para editar)
  const TIPOS_CARGA = [['GRANEL', 'Granel'], ['CARGA_SECA', 'Carga seca'], ['REFRIGERADO', 'Refrigerada'], ['PERIGOSO', 'Perigosa']];

  const situacao = (item) => (!item.ativo ? '<span class="pilula cinza">Inativo</span>'
    : item.em_viagem ? '<span class="pilula azul">Em viagem</span>' : '<span class="pilula verde">Livre</span>');

  // Editar e desativar ficam discretos na linha; desativar só para quem está ativo e fora de viagem.
  function acoes(tipo, item, nome) {
    if (!item.ativo) return '';
    const editar = `<button type="button" class="botao fantasma pequeno" data-editar="${tipo}" data-id="${escapar(item.id)}"
      aria-label="Editar ${escapar(nome)}">${icone('lapis')} Editar</button>`;
    const desativar = item.em_viagem ? '' : `<button type="button" class="botao fantasma perigo pequeno" data-desativar="${tipo}"
      data-id="${escapar(item.id)}" data-nome="${escapar(nome)}" aria-label="Desativar ${escapar(nome)}">Desativar</button>`;
    return `<div class="acoes-linha">${editar}${desativar}</div>`;
  }

  async function carregar() {
    try {
      const base = `/api/v1/transportadoras/${encodeURIComponent(transportadora.id)}`;
      const [motoristas, veiculos] = await Promise.all([api(`${base}/motoristas?size=100`), api(`${base}/veiculos?size=100`)]);
      itens.motoristas = motoristas.items;
      itens.veiculos = veiculos.items;
      document.getElementById('motoristas').innerHTML = motoristas.items.length ? `<table class="tabela estatica"><thead><tr><th>Nome</th>
        <th class="opcional">Telefone</th><th>CNH</th><th class="opcional">Validade</th><th>Situação</th><th></th></tr></thead><tbody>
        ${motoristas.items.map((m) => `<tr><td><strong>${escapar(m.nome)}</strong></td><td class="opcional">${escapar(m.telefone || '—')}</td>
          <td>${escapar(m.cnh_numero)} <span class="chip">cat. ${escapar(m.cnh_categoria)}</span></td>
          <td class="opcional">${formato.data(m.cnh_validade)}</td><td>${situacao(m)}</td>
          <td>${acoes('motoristas', m, m.nome)}</td></tr>`).join('')}
        </tbody></table>` : '<div class="vazio-grande">Nenhum motorista cadastrado.</div>';
      document.getElementById('veiculos').innerHTML = veiculos.items.length ? `<table class="tabela estatica"><thead><tr><th>Placa</th>
        <th>Tipo</th><th class="opcional">Capacidade</th><th class="opcional">Cargas</th><th>Situação</th><th></th></tr></thead><tbody>
        ${veiculos.items.map((v) => `<tr><td><strong>${escapar(v.placa)}</strong></td><td>${formato.veiculo(v.tipo)}
          <br><span class="suave">CNH ${escapar(v.categoria_cnh_exigida)}</span></td>
          <td class="opcional">${formato.toneladas(v.capacidade_kg)}</td>
          <td class="opcional"><span class="chips">${v.tipos_carga.map((t) => `<span class="chip">${formato.tipoCarga(t)}</span>`).join('')}</span></td>
          <td>${situacao(v)}</td>
          <td>${acoes('veiculos', v, v.placa)}</td></tr>`).join('')}
        </tbody></table>` : '<div class="vazio-grande">Nenhum veículo cadastrado.</div>';
      document.querySelectorAll('[data-desativar]').forEach((b) => b.addEventListener('click', () => desativar(b.dataset)));
      document.querySelectorAll('[data-editar]').forEach((b) => b.addEventListener('click', () => {
        const item = itens[b.dataset.editar].find((x) => x.id === b.dataset.id);
        if (item) formulario(b.dataset.editar, item);
      }));
    } catch (erro) {
      document.getElementById('mensagem').innerHTML = erroHtml(erro);
    }
  }

  function desativar({ desativar: tipo, id, nome }) {
    modal({
      titulo: `Desativar ${tipo === 'motoristas' ? 'motorista' : 'veículo'}?`,
      conteudo: `<p><strong>${escapar(nome)}</strong> deixa de ser escalado para novas viagens. O histórico é mantido.</p><div id="erro-modal"></div>`,
      botoes: [{ texto: 'Voltar' }, {
        texto: 'Desativar', classe: 'perigo', async acao(janela) {
          try {
            await api(`/api/v1/transportadoras/${encodeURIComponent(transportadora.id)}/${tipo}/${encodeURIComponent(id)}`, { metodo: 'DELETE' });
            avisoRapido(`${nome} desativado.`);
            carregar();
            return true;
          } catch (erro) { janela.querySelector('#erro-modal').innerHTML = erroHtml(erro); return false; }
        },
      }],
    });
  }

  function formulario(tipo, item = null) {
    const motorista = tipo === 'motoristas';
    const conteudo = motorista ? `
      <div class="campo"><label for="m-nome">Nome <span class="obrigatorio">*</span></label><input id="m-nome" required minlength="3"></div>
      <div class="linha-campos">
        <div class="campo"><label for="m-telefone">Telefone</label><input id="m-telefone" placeholder="(11) 99999-0000"></div>
        <div class="campo"><label for="m-cnh">CNH (11 dígitos) <span class="obrigatorio">*</span></label><input id="m-cnh" inputmode="numeric" maxlength="11"></div>
      </div>
      <div class="linha-campos">
        <div class="campo"><label for="m-categoria">Categoria</label><select id="m-categoria"><option>E</option><option>D</option><option>C</option><option>B</option></select></div>
        <div class="campo"><label for="m-validade">Validade da CNH <span class="obrigatorio">*</span></label><input id="m-validade" type="date"></div>
      </div><div id="erro-modal"></div>` : `
      <div class="linha-campos">
        <div class="campo"><label for="v-placa">Placa <span class="obrigatorio">*</span></label><input id="v-placa" placeholder="ABC1D23" maxlength="7"></div>
        <div class="campo"><label for="v-tipo">Tipo <span class="obrigatorio">*</span></label><select id="v-tipo">
          ${['CARRETA_GRANELEIRA', 'CARRETA_SIDER', 'BITREM_GRANELEIRO', 'TRUCK_BAU', 'CARRETA_FRIGORIFICA', 'TRUCK_FRIGORIFICO', 'CARRETA_TANQUE']
            .map((t) => `<option value="${t}">${formato.veiculo(t)}</option>`).join('')}</select></div>
      </div>
      <div class="linha-campos">
        <div class="campo"><label for="v-capacidade">Capacidade (kg) <span class="obrigatorio">*</span></label><input id="v-capacidade" type="number" min="1" step="100"></div>
        <div class="campo"><label for="v-cnh">CNH exigida</label><select id="v-cnh"><option>E</option><option>D</option><option>C</option><option>B</option></select></div>
      </div>
      <div class="campo"><label>Tipos de carga <span class="obrigatorio">*</span></label><div class="chips">
        ${TIPOS_CARGA.map(([v, t]) => `<label class="chip"><input type="checkbox" name="v-cargas" value="${v}"> ${t}</label>`).join('')}</div></div>
      <div id="erro-modal"></div>`;

    modal({
      titulo: `${item ? 'Editar' : 'Novo'} ${motorista ? 'motorista' : 'veículo'}`,
      conteudo,
      botoes: [{ texto: 'Cancelar' }, {
        texto: item ? 'Salvar' : 'Cadastrar', classe: 'primario', async acao(janela) {
          const v = (id) => janela.querySelector(id).value.trim();
          const corpo = motorista
            ? { nome: v('#m-nome'), telefone: v('#m-telefone') || null, cnhNumero: v('#m-cnh'), cnhCategoria: v('#m-categoria'), cnhValidade: v('#m-validade') || null }
            : { placa: v('#v-placa').toUpperCase(), tipo: v('#v-tipo'), capacidadeKg: Number(v('#v-capacidade')),
                tiposCarga: [...janela.querySelectorAll('input[name=v-cargas]:checked')].map((c) => c.value), categoriaCnhExigida: v('#v-cnh') };
          try {
            const base = `/api/v1/transportadoras/${encodeURIComponent(transportadora.id)}/${tipo}`;
            await api(item ? `${base}/${encodeURIComponent(item.id)}` : base, { metodo: item ? 'PUT' : 'POST', corpo });
            avisoRapido(`${motorista ? 'Motorista' : 'Veículo'} ${item ? 'atualizado' : 'cadastrado'}.`);
            carregar();
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
    if (item) {  // edição: os campos começam com os dados atuais
      const janela = document.querySelector('.modal-fundo:last-child');
      const por = (id, valor) => { const campo = janela.querySelector(id); if (campo) campo.value = valor ?? ''; };
      if (motorista) {
        por('#m-nome', item.nome); por('#m-telefone', item.telefone); por('#m-cnh', item.cnh_numero);
        por('#m-categoria', item.cnh_categoria); por('#m-validade', item.cnh_validade);
      } else {
        por('#v-placa', item.placa); por('#v-tipo', item.tipo); por('#v-capacidade', item.capacidade_kg); por('#v-cnh', item.categoria_cnh_exigida);
        janela.querySelectorAll('input[name=v-cargas]').forEach((c) => { c.checked = item.tipos_carga.includes(c.value); });
      }
    }
  }

  Portal.iniciar({
    ativo: 'frota',
    perfis: ['transportadora'],
    async aoEntrar() {
      const conteudo = document.getElementById('conteudo');
      try {
        transportadora = await api('/api/v1/transportadoras/minha');
      } catch (erro) { conteudo.innerHTML = erroHtml(erro); return; }
      conteudo.innerHTML = `
        <div class="cabecalho"><div><h1>Minha frota</h1>
          <p>Motoristas e veículos da <strong>${escapar(transportadora.nome)}</strong>. Só quem está livre e é compatível
          com a carga é escalado, e só com frota livre a transportadora pode cotar.</p></div></div>
        <div id="mensagem"></div>
        <div class="grade-frota">
          <section class="cartao"><div class="cabecalho-cartao"><h2>${icone('usuario')} Motoristas</h2>
            <button type="button" class="botao primario pequeno" id="novo-motorista">+ Novo motorista</button></div>
            <div id="motoristas" class="carregando">Carregando…</div></section>
          <section class="cartao"><div class="cabecalho-cartao"><h2>${icone('caminhao')} Veículos</h2>
            <button type="button" class="botao primario pequeno" id="novo-veiculo">+ Novo veículo</button></div>
            <div id="veiculos" class="carregando">Carregando…</div></section>
        </div>`;
      document.getElementById('novo-motorista').addEventListener('click', () => formulario('motoristas'));
      document.getElementById('novo-veiculo').addEventListener('click', () => formulario('veiculos'));
      carregar();
      setInterval(carregar, 10000);
    },
  });
})();
