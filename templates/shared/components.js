(function (global) {
  'use strict';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c]));
  }

  function linkify(text) {
    if (!text) return '';
    const urlRegex = /(https?:\/\/[^\s]+)/g;
    return esc(text).replace(urlRegex, url =>
      `<a href="${url}" target="_blank" rel="noopener" style="color:var(--color-accent);word-break:break-all">${url}</a>`
    );
  }

  function toast(container, msg, type, onDone) {
    const color = type === 'error' ? 'var(--color-danger)' :
      type === 'success' ? 'var(--color-success)' :
      type === 'warning' ? 'var(--color-warning)' :
      'var(--color-accent)';
    const duration = type === 'error' ? 8000 : type === 'success' ? 4000 : 3000;
    const el = document.createElement('div');
    el.style.cssText = `position:fixed;bottom:20px;right:20px;background:${color};color:#fff;padding:12px 20px;border-radius:var(--radius-sm);z-index:200;font-size:14px;box-shadow:var(--shadow-lg);max-width:400px`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => {
      el.style.transition = 'opacity 0.3s';
      el.style.opacity = '0';
      setTimeout(() => {
        el.remove();
        if (onDone) onDone();
      }, 300);
    }, duration);
  }

  function badge(role) {
    return `<span class="badge badge-${role}">${esc(role)}</span>`;
  }

  function tag(text, variant) {
    return `<span class="tag tag-${variant || 'neutral'}">${esc(text)}</span>`;
  }

  function stateTag(stato) {
    const cls = stato === 'BOZZA' ? 'tag-bozza' :
      stato.startsWith('PRATICA_ARCHIVIATA') || stato === 'RICONOSCIMENTO_CONCESSO' || stato === 'PRATICA_RESPINTA' ? 'tag-terminal' :
      stato.includes('NON_') || stato.includes('INSUFFICIENTE') ? 'tag-error' :
      'tag-progress';
    return `<span class="tag ${cls}">${stato.replace(/_/g, ' ')}</span>`;
  }

  function skeleton(lines) {
    return Array.from({ length: lines || 3 }, () =>
      `<div class="skeleton skeleton-line" style="width:${60 + Math.random() * 40}%"></div>`
    ).join('');
  }

  function errorBanner(msg, onRetry) {
    const retryBtn = onRetry
      ? `<button class="btn btn-secondary btn-sm" onclick="${onRetry}">Riprova</button>`
      : '';
    return `<div class="error-banner"><span class="error-banner-text">Errore: ${esc(msg)}</span>${retryBtn}</div>`;
  }

  function emptyState(msg) {
    return `<div class="card"><p class="text-muted">${esc(msg)}</p></div>`;
  }

  function loadingState(msg) {
    return `<main><p class="text-muted">${esc(msg || 'Caricamento...')}</p></main>`;
  }

  function debounce(fn, ms) {
    let timer;
    return function (...args) {
      clearTimeout(timer);
      timer = setTimeout(() => fn.apply(this, args), ms || 350);
    };
  }

  global.SharedComponents = {
    esc,
    linkify,
    toast,
    badge,
    tag,
    stateTag,
    skeleton,
    errorBanner,
    emptyState,
    loadingState,
    debounce,
  };
})(typeof window !== 'undefined' ? window : this);
