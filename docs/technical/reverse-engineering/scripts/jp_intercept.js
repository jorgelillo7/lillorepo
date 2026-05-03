// SSL Pinning Bypass + HTTP Interceptor for Jornada Perfecta

Java.perform(function() {

    // ─── 1. TrustManager bypass ───────────────────────────────────────────────
    try {
        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        TrustManagerImpl.verifyChain.implementation = function(a, b, c, d, e, f) {
            return a;
        };
        console.log('[+] TrustManagerImpl hooked');
    } catch(e) { console.log('[-] TrustManagerImpl: ' + e); }

    // ─── 2. OkHttp3 CertificatePinner bypass (todas las firmas posibles) ──────
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        // Firma con Certificate array (la más común)
        try {
            CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(a, b) {
                console.log('[SSL] CertificatePinner(array) bypassed: ' + a);
            };
            console.log('[+] OkHttp3 CertificatePinner (array) hooked');
        } catch(e1) { console.log('[-] CertificatePinner array: ' + e1); }

        // Firma con List
        try {
            CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(a, b) {
                console.log('[SSL] CertificatePinner(list) bypassed: ' + a);
            };
            console.log('[+] OkHttp3 CertificatePinner (list) hooked');
        } catch(e2) { console.log('[-] CertificatePinner list: ' + e2); }
    } catch(e) { console.log('[-] OkHttp3 CertificatePinner: ' + e); }

    // ─── 3. WebViewClient SSL bypass ─────────────────────────────────────────
    try {
        var WebViewClient = Java.use('android.webkit.WebViewClient');
        WebViewClient.onReceivedSslError.implementation = function(view, handler, error) {
            handler.proceed();
        };
        console.log('[+] WebViewClient SSL bypass OK');
    } catch(e) { console.log('[-] WebViewClient: ' + e); }

    // ─── 4. Interceptar OkHttp3 via RealCall.execute y enqueue ───────────────
    try {
        var RealCall = Java.use('okhttp3.internal.connection.RealCall');

        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();
            console.log('\n>>> [REQ] ' + request.method() + ' ' + url);
            logHeaders(request.headers());
            logRequestBody(request);

            var response = this.execute();
            logResponse(response, url);
            return response;
        };

        RealCall.enqueue.implementation = function(callback) {
            var request = this.request();
            var url = request.url().toString();
            console.log('\n>>> [REQ async] ' + request.method() + ' ' + url);
            logHeaders(request.headers());
            logRequestBody(request);
            this.enqueue(callback);
        };

        console.log('[+] RealCall hooked');
    } catch(e) {
        console.log('[-] RealCall: ' + e);
        // Fallback: hook OkHttpClient.newCall
        try {
            var OkHttpClient = Java.use('okhttp3.OkHttpClient');
            OkHttpClient.newCall.implementation = function(request) {
                var url = request.url().toString();
                console.log('\n>>> [newCall] ' + request.method() + ' ' + url);
                return this.newCall(request);
            };
            console.log('[+] OkHttpClient.newCall hooked (fallback)');
        } catch(e2) { console.log('[-] OkHttpClient fallback: ' + e2); }
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────
    function logHeaders(headers) {
        try {
            for (var i = 0; i < headers.size(); i++) {
                var name = headers.name(i).toLowerCase();
                if (name !== 'cookie' && name !== 'authorization') {
                    console.log('    [H] ' + headers.name(i) + ': ' + headers.value(i));
                } else {
                    console.log('    [H] ' + headers.name(i) + ': ***');
                }
            }
        } catch(e) {}
    }

    function logRequestBody(request) {
        try {
            var body = request.body();
            if (body !== null) {
                var Buffer = Java.use('okio.Buffer');
                var buf = Buffer.$new();
                body.writeTo(buf);
                console.log('    [BODY] ' + buf.readUtf8());
            }
        } catch(e) {}
    }

    function logResponse(response, url) {
        try {
            console.log('    [RES] HTTP ' + response.code() + ' <- ' + url);
            var body = response.body();
            if (body !== null) {
                var str = body.string();
                if (str.length < 3000) {
                    console.log('    [RES BODY] ' + str);
                } else {
                    console.log('    [RES BODY] ' + str.substring(0, 3000) + '\n    ...[truncated ' + str.length + ' chars]');
                }
            }
        } catch(e) { console.log('    [RES] error leyendo respuesta: ' + e); }
    }

    console.log('\n[*] Interceptor activo. Navega en la app...\n');
});
