(async () => {
  'use strict';

  const old = document.getElementById('__personal_card_stripe_modal__');
  if (old) old.remove();

  // Stripe publishable key 是前端公开配置。优先从当前页面资源自动发现，
  // 若个人页面尚未加载 billing chunk，则使用本机 HAR 已确认的同商户公钥。
  const HAR_CONFIRMED_PUBLISHABLE_KEY =
    'pk_live_51HOrSwC6h1nxGoI3lTAgRjYVrz4dU3fVOabyCcKR3pbEJguCVAlqCxdxCUvoRh1XWwRacViovU3kLKvpkjh7IqkW00iXQsjo3n';

  async function discoverPublishableKey() {
    const pattern = /pk_(?:live|test)_[A-Za-z0-9]{20,}/;

    // 已发起过 Stripe 请求时，可直接从 Resource Timing URL 中读取 key 参数。
    for (const entry of performance.getEntriesByType('resource')) {
      const match = String(entry.name || '').match(pattern);
      if (match) return match[0];
    }

    // 查找当前文档中的内联配置和 script URL。
    const htmlMatch = document.documentElement.innerHTML.match(pattern);
    if (htmlMatch) return htmlMatch[0];

    // 尝试扫描已加载的同源 JS chunk；跨域失败会被跳过。
    const scripts = [...document.scripts]
      .map((script) => script.src)
      .filter(Boolean)
      .slice(-80);
    for (const src of scripts) {
      try {
        const url = new URL(src, location.href);
        if (url.origin !== location.origin) continue;
        const body = await fetch(url, { credentials: 'include' }).then((r) => r.text());
        const match = body.match(pattern);
        if (match) return match[0];
      } catch (_) {
        // 继续尝试其他 chunk。
      }
    }

    return HAR_CONFIRMED_PUBLISHABLE_KEY;
  }

  const sessionResponse = await fetch('/api/auth/session', {
    credentials: 'include',
    cache: 'no-store'
  });
  if (!sessionResponse.ok) {
    console.error('[绑卡] 当前会话读取失败：', sessionResponse.status);
    return;
  }

  const session = await sessionResponse.json();
  const accountId = session?.account?.id;
  const accessToken = session?.accessToken;
  if (!accountId || !accessToken) {
    console.error('[绑卡] 当前会话缺少账户或访问令牌。');
    return;
  }

  const publishableKey = await discoverPublishableKey();
  console.log('[绑卡] Stripe 前端公钥已自动加载。');

  const commonHeaders = {
    authorization: `Bearer ${accessToken}`,
    'chatgpt-account-id': accountId
  };

  // 每次重新创建 Intent，避免使用已经输出或分享过的 client_secret。
  const intentResponse = await fetch('/backend-api/payments/payment_method', {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...commonHeaders,
      'content-type': 'application/json',
      'x-openai-target-path': '/backend-api/payments/payment_method',
      'x-openai-target-route': '/backend-api/payments/payment_method'
    },
    body: JSON.stringify({ account_id: accountId })
  });

  const intentData = await intentResponse.json().catch(() => ({}));
  if (!intentResponse.ok || !intentData.client_secret) {
    console.error('[绑卡] SetupIntent 创建失败：', intentResponse.status, intentData);
    return;
  }
  const clientSecret = intentData.client_secret;

  if (!window.Stripe) {
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://js.stripe.com/v3/';
      script.async = true;
      script.onload = resolve;
      script.onerror = () => reject(new Error('Stripe.js 加载失败'));
      document.head.appendChild(script);
    });
  }

  const overlay = document.createElement('div');
  overlay.id = '__personal_card_stripe_modal__';
  overlay.style.cssText = [
    'position:fixed', 'inset:0', 'z-index:2147483647',
    'display:flex', 'align-items:center', 'justify-content:center',
    'background:rgba(15,23,42,.62)', 'padding:18px'
  ].join(';');

  const modal = document.createElement('div');
  modal.style.cssText = [
    'width:min(560px,96vw)', 'max-height:92vh', 'overflow:auto',
    'background:#fff', 'border-radius:14px', 'padding:20px',
    'box-shadow:0 24px 70px rgba(0,0,0,.35)',
    'font:14px/1.45 system-ui,-apple-system,Segoe UI,sans-serif',
    'color:#0f172a'
  ].join(';');
  modal.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <strong style="font-size:18px">个人账户添加支付方式</strong>
      <button id="__card_close__" type="button" style="border:0;background:#eee;border-radius:7px;padding:6px 10px;cursor:pointer">关闭</button>
    </div>
    <div style="font-size:12px;color:#64748b;margin-bottom:13px">
      Google Pay 使用 Stripe Express Checkout 保存，银行卡使用 Card Element 保存。
    </div>
    <div id="__google_pay_section__" style="min-height:44px;visibility:hidden">
      <div id="__google_pay_element__"></div>
      <div style="display:flex;align-items:center;gap:10px;margin:15px 0;color:#64748b;font-size:12px">
        <span style="height:1px;background:#d1d5db;flex:1"></span>
        <span>或使用银行卡</span>
        <span style="height:1px;background:#d1d5db;flex:1"></span>
      </div>
    </div>
    <label style="display:block;font-size:12px;font-weight:600;margin-bottom:5px">持卡人姓名</label>
    <input id="__card_name__" autocomplete="cc-name" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:11px;margin-bottom:12px;font:14px system-ui" />
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:12px">
      <label style="display:block;font-size:12px;font-weight:600">账单邮箱
        <input id="__billing_email__" type="email" autocomplete="email" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;margin-top:5px;font:14px system-ui" />
      </label>
      <label style="display:block;font-size:12px;font-weight:600">账单电话
        <input id="__billing_phone__" type="tel" autocomplete="tel" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;margin-top:5px;font:14px system-ui" />
      </label>
    </div>
    <label style="display:block;font-size:12px;font-weight:600;margin-bottom:5px">账单地址</label>
    <input id="__billing_line1__" autocomplete="address-line1" placeholder="地址第一行" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;margin-bottom:8px;font:14px system-ui" />
    <input id="__billing_line2__" autocomplete="address-line2" placeholder="地址第二行（可选）" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;margin-bottom:8px;font:14px system-ui" />
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:8px">
      <input id="__billing_city__" autocomplete="address-level2" placeholder="城市" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;font:14px system-ui" />
      <input id="__billing_state__" autocomplete="address-level1" placeholder="省/州（可选）" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;font:14px system-ui" />
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-bottom:12px">
      <input id="__billing_postal_code__" autocomplete="postal-code" placeholder="邮编" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;font:14px system-ui" />
      <input id="__billing_country__" autocomplete="country" maxlength="2" placeholder="国家代码，例如 US" style="box-sizing:border-box;width:100%;border:1px solid #d1d5db;border-radius:8px;padding:10px;font:14px system-ui;text-transform:uppercase" />
    </div>
    <div id="__card_element__" style="border:1px solid #d1d5db;border-radius:8px;padding:13px;background:#fff"></div>
    <div id="__card_message__" style="min-height:22px;margin-top:12px;color:#b42318"></div>
    <button id="__card_submit__" type="button" style="width:100%;margin-top:8px;border:0;border-radius:9px;padding:11px;background:#0f766e;color:#fff;font-weight:700;cursor:pointer">
      确认绑定
    </button>
  `;
  overlay.appendChild(modal);
  (document.body || document.documentElement).appendChild(overlay);

  const closeButton = modal.querySelector('#__card_close__');
  const submitButton = modal.querySelector('#__card_submit__');
  const cardName = modal.querySelector('#__card_name__');
  const billingEmail = modal.querySelector('#__billing_email__');
  const billingPhone = modal.querySelector('#__billing_phone__');
  const billingLine1 = modal.querySelector('#__billing_line1__');
  const billingLine2 = modal.querySelector('#__billing_line2__');
  const billingCity = modal.querySelector('#__billing_city__');
  const billingState = modal.querySelector('#__billing_state__');
  const billingPostalCode = modal.querySelector('#__billing_postal_code__');
  const billingCountry = modal.querySelector('#__billing_country__');
  const message = modal.querySelector('#__card_message__');
  const googlePaySection = modal.querySelector('#__google_pay_section__');
  closeButton.onclick = () => overlay.remove();
  submitButton.disabled = true;
  submitButton.style.opacity = '.55';
  submitButton.textContent = '等待卡输入框加载';

  let cardReady = false;
  let flowBusy = false;
  let resolveCardReady;
  const cardReadyPromise = new Promise((resolve) => {
    resolveCardReady = resolve;
  });

  const stripe = window.Stripe(publishableKey);
  const elements = stripe.elements({ locale: 'auto' });
  const cardElement = elements.create('card', {
    hidePostalCode: true,
    style: {
      base: {
        color: '#0f172a',
        fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif',
        fontSize: '16px',
        '::placeholder': { color: '#94a3b8' }
      },
      invalid: { color: '#b42318' }
    }
  });
  cardElement.mount('#__card_element__');
  cardElement.on('ready', () => {
    cardReady = true;
    resolveCardReady(true);
    message.style.color = '#087443';
    message.textContent = '卡输入框已加载。';
    submitButton.disabled = false;
    submitButton.style.opacity = '1';
    submitButton.textContent = '确认绑定';
  });
  cardElement.on('loaderror', (event) => {
    cardReady = false;
    resolveCardReady(false);
    message.style.color = '#b42318';
    message.textContent = `Stripe 输入框加载失败：${event?.error?.message || 'loaderror'}`;
    console.error('[绑卡] Card Element loaderror：', event);
  });
  cardElement.on('change', (event) => {
    if (event.error) {
      message.style.color = '#b42318';
      message.textContent = event.error.message;
    } else if (event.complete) {
      message.style.color = '#087443';
      message.textContent = '卡资料填写完成，可以确认绑定。';
    } else {
      message.textContent = '';
    }
  });

  async function readPaymentMethods() {
    const response = await fetch(
      `/backend-api/payments/payment_methods?account_id=${encodeURIComponent(accountId)}`,
      {
        credentials: 'include',
        cache: 'no-store',
        headers: {
          ...commonHeaders,
          'x-openai-target-path': '/backend-api/payments/payment_methods',
          'x-openai-target-route': '/backend-api/payments/payment_methods'
        }
      }
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(`支付方式查询失败 (${response.status})：${JSON.stringify(data)}`);
    }
    return data;
  }

  async function waitForPaymentMethod(paymentMethodId) {
    for (let attempt = 0; attempt < 8; attempt += 1) {
      const list = await readPaymentMethods();
      const method = (list.payment_methods || []).find(
        (item) => item?.id === paymentMethodId
      );
      if (method) return { list, method };
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error(`SetupIntent 已成功，但查询结果没有 ${paymentMethodId}`);
  }

  async function ensureDefaultPaymentMethod(paymentMethodId, firstList) {
    if (firstList.default_payment_method_id === paymentMethodId) {
      return { source: 'confirmCardSetup', list: firstList };
    }

    const response = await fetch('/backend-api/payments/payment_method/default', {
      method: 'POST',
      credentials: 'include',
      headers: {
        ...commonHeaders,
        'content-type': 'application/json',
        'x-openai-target-path': '/backend-api/payments/payment_method/default',
        'x-openai-target-route': '/backend-api/payments/payment_method/default'
      },
      body: JSON.stringify({
        account_id: accountId,
        payment_method_id: paymentMethodId
      })
    });
    const responseText = await response.text();
    if (!response.ok) {
      throw new Error(`默认支付方式更新失败 (${response.status})：${responseText}`);
    }

    for (let attempt = 0; attempt < 8; attempt += 1) {
      const list = await readPaymentMethods();
      if (list.default_payment_method_id === paymentMethodId) {
        return { source: 'payment_method/default fallback', list };
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    throw new Error(`支付方式 ${paymentMethodId} 已保存，但默认状态没有更新`);
  }

  async function finalizeSuccessfulSetup(setupIntent, source) {
    if (setupIntent?.status !== 'succeeded') {
      throw new Error(`SetupIntent 状态为 ${setupIntent?.status || 'unknown'}`);
    }
    const paymentMethodId =
      typeof setupIntent.payment_method === 'string'
        ? setupIntent.payment_method
        : setupIntent.payment_method?.id;
    if (!paymentMethodId) throw new Error('SetupIntent 没有返回 payment_method ID');

    const saved = await waitForPaymentMethod(paymentMethodId);
    const defaultResult = await ensureDefaultPaymentMethod(paymentMethodId, saved.list);
    const result = {
      source,
      setupIntent,
      paymentMethodId,
      paymentMethod: saved.method,
      defaultSource: defaultResult.source,
      verifiedPaymentMethods: defaultResult.list
    };
    window.__personalPaymentMethodBind = result;
    console.log('[绑卡] 保存与查询均已验证：', result);
    message.style.color = '#087443';
    message.textContent = `${source} 已保存并设为默认：${paymentMethodId}`;
    submitButton.textContent = '绑定成功';
    submitButton.disabled = true;
    return result;
  }

  function readBillingDetails(name, { requireAddress = false } = {}) {
    const rawAddress = {
      line1: billingLine1.value.trim(),
      line2: billingLine2.value.trim(),
      city: billingCity.value.trim(),
      state: billingState.value.trim(),
      postal_code: billingPostalCode.value.trim(),
      country: billingCountry.value.trim().toUpperCase()
    };
    const requiredAddressFields = ['line1', 'city', 'postal_code', 'country'];
    if (requireAddress) {
      const missing = requiredAddressFields.filter((field) => !rawAddress[field]);
      if (missing.length) {
        throw new Error(`请填写完整账单地址：${missing.join(', ')}`);
      }
    }
    if (rawAddress.country && !/^[A-Z]{2}$/.test(rawAddress.country)) {
      throw new Error('国家必须使用 ISO 3166-1 alpha-2 两位代码，例如 US。');
    }

    const details = {};
    if (name) details.name = name;
    if (billingEmail.value.trim()) details.email = billingEmail.value.trim();
    if (billingPhone.value.trim()) details.phone = billingPhone.value.trim();
    const address = Object.fromEntries(
      Object.entries(rawAddress).filter(([, value]) => value),
    );
    if (Object.keys(address).length) details.address = address;
    return details;
  }

  function referenceConfirmData(card, billingDetails) {
    return {
      payment_method: {
        card,
        ...(Object.keys(billingDetails).length ? { billing_details: billingDetails } : {}),
        allow_redisplay: 'always'
      },
      set_as_default_payment_method: true
    };
  }

  const googlePayState = {
    integration: 'expressCheckout',
    ready: false,
    availablePaymentMethods: null,
    lastError: null
  };
  window.__personalPaymentMethodBindGooglePay = googlePayState;

  function setGooglePayVisible(visible) {
    googlePaySection.hidden = !visible;
    googlePaySection.style.visibility = visible ? 'visible' : 'hidden';
    googlePaySection.style.minHeight = visible ? '0' : '44px';
  }

  try {
    const googlePayElements = stripe.elements({
      clientSecret,
      locale: 'auto'
    });
    const expressCheckoutElement = googlePayElements.create('expressCheckout', {
      paymentMethods: {
        amazonPay: 'never',
        applePay: 'never',
        googlePay: 'always',
        klarna: 'never',
        link: 'never',
        paypal: 'never'
      },
      layout: {
        maxColumns: 1,
        maxRows: 1,
        overflow: 'auto'
      }
    });

    expressCheckoutElement.on('ready', (event) => {
      const availablePaymentMethods = event?.availablePaymentMethods || null;
      const googlePayAvailable =
        availablePaymentMethods?.googlePay === true ||
        availablePaymentMethods?.google_pay === true;
      googlePayState.ready = googlePayAvailable;
      googlePayState.availablePaymentMethods = availablePaymentMethods;
      setGooglePayVisible(googlePayAvailable);
      console.log('[绑卡] Express Checkout Google Pay 可用性：', {
        googlePayAvailable,
        availablePaymentMethods
      });
    });

    expressCheckoutElement.on('loaderror', (event) => {
      const error = event?.error || new Error('Express Checkout loaderror');
      googlePayState.ready = false;
      googlePayState.lastError = error?.message || String(error);
      setGooglePayVisible(false);
      console.error('[绑卡] Express Checkout 加载失败：', error);
    });

    expressCheckoutElement.on('confirm', async () => {
      if (flowBusy) return;
      flowBusy = true;
      submitButton.disabled = true;
      submitButton.style.opacity = '.65';
      message.style.color = '#334155';
      message.textContent = '正在通过 Google Pay 验证并绑定……';

      try {
        const billingDetails = readBillingDetails(cardName.value.trim());
        const result = await stripe.confirmSetup({
          elements: googlePayElements,
          clientSecret,
          redirect: 'if_required',
          confirmParams: {
            return_url: location.href,
            payment_method_data: {
              allow_redisplay: 'always',
              ...(Object.keys(billingDetails).length
                ? { billing_details: billingDetails }
                : {})
            }
          }
        });
        if (result?.error) throw result.error;

        let setupIntent = result?.setupIntent || null;
        if (!setupIntent) {
          const retrieved = await stripe.retrieveSetupIntent(clientSecret);
          if (retrieved?.error) throw retrieved.error;
          setupIntent = retrieved?.setupIntent || null;
        }
        await finalizeSuccessfulSetup(setupIntent, 'Google Pay');
      } catch (error) {
        googlePayState.lastError = error?.message || String(error);
        message.style.color = '#b42318';
        message.textContent = googlePayState.lastError;
        console.error('[绑卡] Google Pay SetupIntent 确认失败：', error);
        flowBusy = false;
        submitButton.disabled = !cardReady;
        submitButton.style.opacity = '1';
      }
    });

    expressCheckoutElement.mount('#__google_pay_element__');
  } catch (error) {
    googlePayState.lastError = error?.message || String(error);
    setGooglePayVisible(false);
    console.error('[绑卡] Express Checkout 初始化失败：', error);
  }

  submitButton.onclick = async () => {
    if (flowBusy) return;
    flowBusy = true;
    submitButton.disabled = true;
    submitButton.style.opacity = '.65';
    message.style.color = '#334155';
    message.textContent = '正在验证并绑定……';

    try {
      if (!cardReady) {
        const ready = await Promise.race([
          cardReadyPromise,
          new Promise((resolve) => setTimeout(() => resolve(false), 15000))
        ]);
        if (!ready || !cardReady) {
          throw new Error('Stripe Card Element 尚未 ready；检查 js.stripe.com iframe 是否被浏览器扩展或跟踪保护拦截。');
        }
      }

      const name = cardName.value.trim();
      if (!name) throw new Error('请输入持卡人姓名。');
      const billingDetails = readBillingDetails(name, { requireAddress: true });

      const result = await stripe.confirmCardSetup(
        clientSecret,
        referenceConfirmData(cardElement, billingDetails)
      );

      if (result.error) throw result.error;
      await finalizeSuccessfulSetup(result.setupIntent, '银行卡');
    } catch (error) {
      message.style.color = '#b42318';
      message.textContent = error?.message || String(error);
      console.error('[绑卡] Stripe 确认失败：', error);
      flowBusy = false;
    } finally {
      submitButton.disabled = flowBusy || !cardReady;
      submitButton.style.opacity = '1';
    }
  };
})();
