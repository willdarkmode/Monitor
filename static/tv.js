(function() {
    /* ─── Helpers ──────────────────────────────── */
    const escapeHtml = value => String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
    
    const brl = v => Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0});
    const pct = v => `${Number(v||0).toFixed(1).replace('.',',')}%`;
    const n   = v => { const x = Number(v||0); return isFinite(x) ? x : 0; };
    const ts  = v => {
        if (!v) return '—';
        const d = new Date(v);
        return isNaN(d.getTime()) ? v : d.toLocaleString('pt-BR',{hour:'2-digit',minute:'2-digit',day:'2-digit',month:'2-digit'});
    };

    let lastGood = null, fails = 0;
    let lastValues = {};
    let rankOffset = 0;
    let rankGroupHeight = 0;
    let rankLastFrame = performance.now();
    let rankRaf = null;
    let rankPaused = false;
    const rankSpeed = 18;
    let comparativoMostrarPercentual = false;
    let comparativoAtual = null;

    /* ─── Animação de contagem ────────────────── */
    function animateValue(element, start, end, duration, formatter = brl) {
        if (!element) return;
        const range = end - start;
        if (range === 0) {
            element.textContent = formatter(end);
            return;
        }
        const startTime = performance.now();
        const step = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const current = start + range * progress;
            element.textContent = formatter(current);
            if (progress < 1) {
                requestAnimationFrame(step);
            } else {
                element.textContent = formatter(end);
            }
        };
        requestAnimationFrame(step);
    }

    function flashKPI(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.add('flash');
        setTimeout(() => el.classList.remove('flash'), 600);
    }

    function updateWithAnimation(id, newVal, formatter = brl) {
        const el = document.getElementById(id);
        if (!el) return;
        const oldVal = lastValues[id] !== undefined ? lastValues[id] : 0;
        if (oldVal !== newVal) {
            flashKPI(id);
            animateValue(el, oldVal, newVal, 800, formatter);
        } else {
            el.textContent = formatter(newVal);
        }
        lastValues[id] = newVal;
    }

    function renderComparativoAnoAnterior() {
        const labelEl = document.getElementById('comparativoLabel');
        const valueEl = document.getElementById('comparativoAnoAnterior');

        if (!labelEl || !valueEl || !comparativoAtual) return;

        const ano = comparativoAtual.ano;
        const valor = n(comparativoAtual.valor);
        const variacao = n(comparativoAtual.variacao_percentual);

        labelEl.textContent = `Período ${ano}`;

        if (comparativoMostrarPercentual) {
            const sinal = variacao > 0 ? '+' : '';
            valueEl.textContent = `${sinal}${pct(variacao)}`;

            if (variacao >= 0) {
                valueEl.className = 'ritmo-val c-green';
            } else {
                valueEl.className = 'ritmo-val c-red';
            }
        } else {
            valueEl.textContent = brl(valor);
            valueEl.className = 'ritmo-val';
        }
    }

    /* ─── Renderização principal ──────────────── */
    function render(d, cached) {
        if (!d) return;

        const fat   = d.faturamento || {};
        const est   = d.estoque     || {};
        const meta  = d.metas       || {};
        const ritmo = d.ritmo_meta  || {};

        const fatPrev  = n(fat['Faturado + Previsto']);
        const faturado = n(fat['Total Faturado']);
        const previsto = n(fat['Total Previsto']);
        const chance   = n(fat['Grande Chance']);
        const devol    = n(fat['Devoluções']);
        const estoque  = n(est['Estoque Total']);
        const metaBase = n(meta['META_BASE'] || meta['Meta Base'] || 0);
        const percent  = metaBase > 0 ? (fatPrev / metaBase) * 100 : 0;
        const falta    = Math.max(metaBase - fatPrev, 0);

        // Header
        if (d.periodo) {
            document.getElementById('periodo').textContent = `${d.periodo.inicio} — ${d.periodo.fim}`;
        }
        document.getElementById('atualizado').textContent = ts(d.atualizado_em) + (cached ? ' · cache' : '');

        // KPIs com animação
        updateWithAnimation('totalFaturado', faturado);
        updateWithAnimation('totalPrevisto', previsto);
        updateWithAnimation('grandeChance', chance);
        updateWithAnimation('devolucoes', devol);
        updateWithAnimation('estoqueTotal', estoque);

        // Meta panel
        const heroFatEl = document.getElementById('heroFat');
        heroFatEl.innerHTML = `${brl(fatPrev)}<span> de ${brl(metaBase)}</span>`;

        const pctEl = document.getElementById('percentualMeta');
        const oldPct = lastValues['percentualMeta'] !== undefined ? lastValues['percentualMeta'] : 0;
        if (oldPct !== percent) {
            animateValue(pctEl, oldPct, percent, 600, pct);
            pctEl.className = 'meta-pct ' + colorClass(percent);
        } else {
            pctEl.textContent = pct(percent);
        }
        lastValues['percentualMeta'] = percent;

        document.getElementById('barraMeta').style.width = `${Math.min(percent,100)}%`;
        updateWithAnimation('faltaMeta', falta);
        updateWithAnimation('metaBase', metaBase);

        const necDia = n(ritmo.necessario_por_dia_util);
        updateWithAnimation('necessarioDia', necDia);

        comparativoAtual = d.comparativo_ano_anterior || null;
        renderComparativoAnoAnterior();

        // Ranking (com rolagem infinita)
        renderRanking(fat['Vendedores'] || []);

        // Ticker
        buildTicker(d, percent, cached);
    }

    function colorClass(p) {
        if (p >= 100) return 'c-green';
        if (p >= 70)  return 'c-amber';
        return 'c-red';
    }

    function rankPctClass(p) {
        if (p >= 100) return 'rank-pct-ok';
        if (p >= 70)  return 'rank-pct-warn';
        return 'rank-pct-bad';
    }

    function startRankScroller() {
        if (rankRaf) return;

        const step = now => {
            const track = document.getElementById('rankTrack');
            const dt = Math.min((now - rankLastFrame) / 1000, 0.08);
            rankLastFrame = now;

            if (track && rankGroupHeight > 0 && !rankPaused) {
                rankOffset += rankSpeed * dt;

                if (rankOffset >= rankGroupHeight) {
                    rankOffset = rankOffset % rankGroupHeight;
                }

                track.style.transform = `translate3d(0, ${-rankOffset}px, 0)`;
            }

            rankRaf = requestAnimationFrame(step);
        };

        rankLastFrame = performance.now();
        rankRaf = requestAnimationFrame(step);
    }

    let lastRankingSignature = '';

    function renderRanking(vendedores) {
        const track = document.getElementById('rankTrack');
        if (!track) return;

        if (!vendedores.length) {
            const emptySignature = 'empty';

            if (lastRankingSignature !== emptySignature) {
                track.innerHTML = '<div style="padding:24px 0;color:var(--muted);font-size:14px">Sem dados no período</div>';
                lastRankingSignature = emptySignature;
            }

            document.getElementById('rankSub').textContent = 'Aguardando dados';
            return;
        }

        // Garante ordem correta mesmo se a API vier fora de ordem
        vendedores = [...vendedores].sort((a, b) => n(b.Total) - n(a.Total));

        // Assinatura estável da lista.
        // Inclui nome, total, faturado, previsto e meta.
        const rankingSignature = JSON.stringify(
            vendedores.map(v => ({
                nome: v.Vendedor || v.vendedor || 'Sem nome',
                total: n(v.Total),
                faturado: n(v.Faturado),
                previsto: n(v.Previsto),
                meta: n(v.Meta)
            }))
        );

        document.getElementById('rankSub').textContent =
            `${vendedores.length} vendedor${vendedores.length > 1 ? 'es' : ''} no período`;

        // Se nada mudou, não mexe no DOM.
        // Isso evita o flick e mantém a posição atual da rolagem.
        if (rankingSignature === lastRankingSignature) {
            return;
        }

        lastRankingSignature = rankingSignature;


        const itemsHTML = vendedores.map((v, i) => {
            const nome      = escapeHtml(v.Vendedor || v.vendedor || 'Sem nome');
            const total     = n(v.Total);
            const faturado  = n(v.Faturado);
            const previsto  = n(v.Previsto);
            const metaV     = n(v.Meta);
            const percentV  = metaV > 0 ? (total / metaV) * 100 : 0;
            const barW      = metaV > 0 ? Math.min(percentV, 100) : 0;
            const metaOk    = metaV > 0 && percentV >= 100;
            const pos       = i + 1;

            return `
                <div class="rank-item">
                    <div class="rank-item-top">
                        <div class="rank-num rank-num-${pos <= 3 ? pos : ''}">${pos}</div>
                        <div class="rank-name">${nome}</div>
                        <div class="rank-total">${brl(total)}</div>
                    </div>
                    <div class="rank-bar-wrap">
                        <div class="rank-bar-fill ${metaOk ? 'rank-bar-fill-ok' : ''}" style="width:${barW}%"></div>
                    </div>
                    <div class="rank-detail">
                        <span>Fat ${brl(faturado)} · Prev ${brl(previsto)}</span>
                        <span class="${rankPctClass(percentV)}">${pct(percentV)}</span>
                    </div>
                </div>
            `;
        }).join('');

        const oldHeight = rankGroupHeight || 1;
        const oldProgress = oldHeight > 0 ? rankOffset / oldHeight : 0;

        track.innerHTML = `
            <div class="rank-group">${itemsHTML}</div>
            <div class="rank-group" aria-hidden="true">${itemsHTML}</div>
        `;

        const firstGroup = track.querySelector('.rank-group');
        const newHeight = firstGroup ? firstGroup.offsetHeight : 0;

        rankGroupHeight = newHeight;

        if (rankGroupHeight > 0) {
            rankOffset = Math.min(oldProgress * rankGroupHeight, rankGroupHeight - 1);
            track.style.transform = `translate3d(0, ${-rankOffset}px, 0)`;
        }

    }

    /* ─── Ticker ───────────────────────────────── */
    function buildTicker(d, percent, cached) {
        const fat      = d.faturamento || {};
        const vendedores = fat['Vendedores'] || [];
        const lider    = vendedores[0];
        const ritmo    = d.ritmo_meta || {};
        const necDia   = n(ritmo.necessario_por_dia_util);

        let html = '';
        if (lider) html += `<span>🏆 Líder: ${lider.Vendedor || lider.vendedor} — ${brl(n(lider.Total))}</span>`;
        if (ritmo.alvo === 'SUPER_META_ATINGIDA') {
            html += '<span class="highlight">Super meta atingida!</span>';
        } else if (ritmo.alvo === 'SUPER_META') {
            html += `<span>Meta atingida · Super meta: ${brl(necDia)}/dia</span>`;
        } else {
            html += `<span>${pct(percent)} da meta · Necessário: ${brl(necDia)}/dia útil</span>`;
        }
        if (cached || fails > 0) html += '<span>⚠ Exibindo cache</span>';
        html += `<span>P&R Automação Industrial</span>`;

        document.getElementById('ticker').innerHTML = html + '&nbsp;&nbsp;&nbsp;' + html;
    }

    /* ─── Relógio em tempo real ────────────────── */
    function updateClock() {
        const now = new Date();
        document.getElementById('relogio').textContent = now.toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
    }
    updateClock();
    setInterval(updateClock, 1000);

    /* ─── Fetch ────────────────────────────────── */
    async function load() {
        const ctrl    = new AbortController();
        const timeout = setTimeout(() => ctrl.abort(), 20000);
        try {
            const r = await fetch('/api/dashboard?ts=' + Date.now(), { signal: ctrl.signal, cache: 'no-store' });
            clearTimeout(timeout);
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const d = await r.json();
            if (!d?.faturamento) throw new Error('Sem dados');
            lastGood = d;
            fails    = 0;
            try { localStorage.setItem('_dash_cache', JSON.stringify(d)); } catch(e) {}
            render(d, false);
        } catch(e) {
            clearTimeout(timeout);
            console.warn('[dashboard]', e.message);
            fails++;
            if (lastGood) { render(lastGood, true); return; }
            try {
                const c = localStorage.getItem('_dash_cache');
                if (c) { lastGood = JSON.parse(c); render(lastGood, true); return; }
            } catch(e2) {}
            document.getElementById('ticker').textContent = 'Aguardando primeira carga válida...';
        }
    }

    load();
    startRankScroller();

    setInterval(load, 60_000);
    setInterval(() => {
        comparativoMostrarPercentual = !comparativoMostrarPercentual;
        renderComparativoAnoAnterior();
    }, 5000);
    setInterval(() => location.reload(), 4 * 60 * 60_000);
})();
