// Small enhancements; every page also works without JavaScript.
document.querySelectorAll('[data-autosubmit]').forEach(function (el) {
  el.addEventListener('change', function () { if (el.form) el.form.submit(); });
});

// Toast: a brief, auto-dismissing confirmation that doesn't require a page reload.
function showToast(message, kind) {
  var stack = document.getElementById('toast-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toast-stack';
    stack.className = 'toast-stack';
    stack.setAttribute('role', 'status');
    stack.setAttribute('aria-live', 'polite');
    document.body.appendChild(stack);
  }
  var toast = document.createElement('div');
  toast.className = 'toast' + (kind === 'error' ? ' is-error' : '');
  toast.textContent = message;
  stack.appendChild(toast);
  requestAnimationFrame(function () { toast.classList.add('is-in'); });
  setTimeout(function () {
    toast.classList.remove('is-in');
    setTimeout(function () { toast.remove(); }, 250);
  }, 2400);
}

// Add to cart without a full page reload: updates the header cart count and
// gives the button instant feedback. Falls back to a normal form submit
// (full reload, server-rendered flash message) if JS or the request fails,
// and never intercepts "Buy now", which needs to navigate to /cart.
document.querySelectorAll('form[data-cart-form]').forEach(function (form) {
  var lastClicked = null;
  form.querySelectorAll('button[type="submit"]').forEach(function (b) {
    b.addEventListener('click', function () { lastClicked = b; });
  });
  form.addEventListener('submit', function (e) {
    var submitter = e.submitter || lastClicked || form.querySelector('button[type="submit"]');
    if (submitter && submitter.name === 'go') return; // Buy now: real navigation to /cart
    if (!submitter || submitter.disabled) { e.preventDefault(); return; }
    var btn = submitter;
    e.preventDefault();
    var original = btn.textContent;
    btn.disabled = true;
    btn.classList.add('is-busy');
    fetch(form.action, {
      method: 'POST',
      body: new FormData(form),
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var cartLink = document.querySelector('.nav .cart');
        var badge = cartLink && cartLink.querySelector('.badge');
        if (badge) {
          badge.textContent = data.cart_count;
          badge.classList.remove('is-pulsing');
          void badge.offsetWidth; // restart the animation
          badge.classList.add('is-pulsing');
        }
        if (cartLink) cartLink.setAttribute('aria-label', 'Cart, ' + data.cart_count + ' items');
        showToast(data.message, data.ok ? 'ok' : 'error');
        btn.classList.remove('is-busy');
        if (data.ok) {
          btn.textContent = 'Added ✓';
          btn.classList.add('is-added');
          setTimeout(function () {
            btn.textContent = original;
            btn.classList.remove('is-added');
            btn.disabled = false;
          }, 1400);
        } else {
          btn.textContent = 'Sold out';
          btn.disabled = true;
        }
      })
      .catch(function () {
        btn.disabled = false;
        btn.classList.remove('is-busy');
        form.submit(); // network/JS error: fall back to a normal page submit
      });
  });
});

document.querySelectorAll('form[data-confirm]').forEach(function (form) {
  form.addEventListener('submit', function (e) {
    if (!window.confirm(form.dataset.confirm)) e.preventDefault();
  });
});

// Product form: swap the picture choices when the category changes.
(function () {
  var cat = document.getElementById('f-category');
  var pick = document.getElementById('icon-pick');
  if (!cat || !pick) return;
  var icons = JSON.parse(pick.dataset.icons || '{}');
  cat.addEventListener('change', function () {
    var list = icons[cat.value] || [];
    pick.innerHTML = list.map(function (ic, i) {
      return '<label title="Use ' + ic + '"><input type="radio" name="icon" value="' + ic + '"' +
        (i === 0 ? ' checked' : '') + '><span aria-hidden="true">' + ic + '</span><span class="sr">Picture ' + (i + 1) + '</span></label>';
    }).join('');
  });
})();

// Product page gallery: click a thumbnail to show it large.
(function () {
  var main = document.getElementById('gallery-main');
  if (!main) return;
  document.querySelectorAll('.thumb[data-full]').forEach(function (t) {
    t.addEventListener('click', function (e) {
      e.preventDefault();
      main.src = t.dataset.full;
      document.querySelectorAll('.thumb').forEach(function (x) { x.classList.remove('is-active'); });
      t.classList.add('is-active');
    });
  });
})();

// Product form: preview new photos and let the user pick one as the cover.
(function () {
  var input = document.querySelector('[data-photo-input]');
  var grid = document.getElementById('new-photos');
  if (!input || !grid) return;
  var zone = input.closest('.dropzone');
  ['dragenter', 'dragover'].forEach(function (ev) { zone.addEventListener(ev, function () { zone.classList.add('drag'); }); });
  ['dragleave', 'drop'].forEach(function (ev) { zone.addEventListener(ev, function () { zone.classList.remove('drag'); }); });
  input.addEventListener('change', function () {
    grid.innerHTML = '';
    var hasCover = !!document.querySelector('input[name="cover"]:not([data-new])');
    Array.prototype.forEach.call(input.files, function (file, i) {
      var box = document.createElement('div');
      box.className = 'photo';
      var img = document.createElement('img');
      img.alt = file.name;
      img.src = URL.createObjectURL(file);
      var tag = document.createElement('span');
      tag.className = 'new-tag';
      tag.textContent = 'New: ' + file.name.slice(0, 18);
      var label = document.createElement('label');
      label.className = 'photo-opt';
      label.innerHTML = '<input type="radio" name="cover" data-new value="new-' + i + '"' + (!hasCover && i === 0 ? ' checked' : '') + '> Cover';
      box.appendChild(img); box.appendChild(tag); box.appendChild(label);
      grid.appendChild(box);
    });
  });
})();

// Logo and banner: show the chosen file name and a preview.
document.querySelectorAll('input[data-preview]').forEach(function (input) {
  input.addEventListener('change', function () {
    var kind = input.dataset.preview;
    var name = document.querySelector('[data-preview-name="' + kind + '"]');
    var file = input.files[0];
    if (!file) return;
    if (name) name.textContent = 'Selected: ' + file.name;
    var current = input.closest('.img-row').querySelector('.img-current');
    if (current) {
      var img = document.createElement('img');
      img.className = current.className.replace('img-empty', '');
      img.src = URL.createObjectURL(file);
      img.alt = 'New ' + kind;
      current.replaceWith(img);
    }
  });
});
