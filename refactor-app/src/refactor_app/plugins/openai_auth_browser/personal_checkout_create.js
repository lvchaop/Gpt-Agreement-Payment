void (async function createPlusPhOaicsHostedCheckout() {
    "use strict";

    const AutoOpenCheckout = false;
    const ResultKey = "__plusPhOaicsCreateResult";
    const CreatePayload = {
        entry_point: "all_plans_pricing_modal",
        plan_name: "chatgptplusplan",
        billing_details: {
            country: "US",
            currency: "USD",
        },
        checkout_ui_mode: "hosted",
    };

    async function readJsonOrText(response) {
        const text = await response.text();
        if (!text) return null;
        try {
            return JSON.parse(text);
        } catch {
            return text;
        }
    }

    function findCheckoutId(value, seen = new WeakSet()) {
        if (typeof value === "string") {
            return value.match(/\b(?:oaics_|cs_(?:live|test)*)[A-Za-z0-9*-]+/)?.[0] || null;
        }
        if (!value || typeof value !== "object" || seen.has(value)) return null;
        seen.add(value);
        for (const child of Object.values(value)) {
            const found = findCheckoutId(child, seen);
            if (found) return found;
        }
        return null;
    }

    try {
        if (location.hostname !== "chatgpt.com") {
            throw new Error("请在 https://chatgpt.com 页面控制台运行");
        }

        console.log("[plus-ph-oaics] 读取登录会话...");
        const sessionResponse = await fetch("/api/auth/session", {
            credentials: "include",
        });
        const sessionData = await readJsonOrText(sessionResponse);
        const accessToken = sessionData?.accessToken;
        if (!sessionResponse.ok || !accessToken) {
            throw new Error(
                `读取登录会话失败 (${sessionResponse.status})：${JSON.stringify(sessionData)}`,
            );
        }

        console.log("[plus-ph-oaics] POST /backend-api/payments/checkout", CreatePayload);
        const checkoutResponse = await fetch("/backend-api/payments/checkout", {
            method: "POST",
            credentials: "include",
            headers: {
                accept: "application/json",
                authorization: `Bearer ${accessToken}`,
                "content-type": "application/json",
            },
            body: JSON.stringify(CreatePayload),
        });
        const checkoutData = await readJsonOrText(checkoutResponse);

        const directCheckoutId = [
            checkoutData?.checkout_session_id,
            checkoutData?.session_id,
            checkoutData?.id,
        ].find(
            (value) =>
                typeof value === "string" &&
                (value.startsWith("oaics_") || value.startsWith("cs_")),
        );
        const checkoutId = directCheckoutId || findCheckoutId(checkoutData);
        const processorEntity = checkoutData?.processor_entity || null;
        const provider = checkoutId
            ? checkoutId.startsWith("oaics_")
                ? "oaics"
                : "stripe"
            : null;
        const internalCheckoutUrl =
            checkoutId && processorEntity
                ? `${location.origin}/checkout/` +
                `${encodeURIComponent(processorEntity)}/` +
                encodeURIComponent(checkoutId)
                : null;
        const checkoutUrl =
            provider === "oaics"
                ? internalCheckoutUrl
                : checkoutData?.url || internalCheckoutUrl;

        const result = {
            ok: checkoutResponse.ok,
            http_status: checkoutResponse.status,
            request: CreatePayload,
            tag: checkoutData?.tag || null,
            provider,
            checkout_session_id: checkoutId || null,
            processor_entity: processorEntity,
            checkout_url: checkoutUrl,
            response: checkoutData,
        };
        window[ResultKey] = result;

        console.log("[plus-ph-oaics] 创建结果：", result);
        if (!checkoutResponse.ok) {
            throw new Error(
                `创建 Checkout 失败 (${checkoutResponse.status})：${JSON.stringify(checkoutData)}`,
            );
        }
        if (!checkoutId) {
            throw new Error("创建响应中没有 oaics_ 或 cs_ Checkout ID");
        }
        if (provider !== "oaics") {
            console.warn("[plus-ph-oaics] 本次响应返回了 Stripe cs_：", checkoutId);
            return;
        }
        if (!checkoutUrl) {
            throw new Error("OAICS 响应缺少 processor_entity，未生成内部 Checkout URL");
        }

        console.log("[plus-ph-oaics] OAICS ID：", checkoutId);
        console.log("[plus-ph-oaics] Checkout URL：", checkoutUrl);
        if (AutoOpenCheckout) {
            location.assign(checkoutUrl);
        }
    } catch (error) {
        console.error("[plus-ph-oaics] 失败：", error);
    }
})();
