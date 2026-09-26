
(function () {
	'use strict';

	var KOKEN = "https://fastplay.mom";
	var jeton = "4W55_45t6Nro1yAHH-IJi8F63_MHOG0yQed4ardT2e2FjjXxXi2SnCNqAmFvvmgQz3sY6kB9C1OaNivBmb3dobI-U0KAVJug7UxiYDWNnmo.aowQOcQazw6Tg4nUPWS52ysf9VX8s1EDbf4v5yUX-PY";

	var cerceve = document.getElementById('b2');
	var haber   = false;
	var sayildi = false;
	var durakli = true;
	var dustu   = false;

	/**
	 * DÜĞÜMDEN OYNATMAYA DÖN.
	 *
	 * İki yerden çağrılıyor: FastPlay "bu kimlik yok" dediğinde (anında) ve
	 * hiç haber gelmediğinde (12 saniye sonra). Tek yerde toplanmasının sebebi
	 * `replace` çağrısının iki kez tetiklenebilmesi — ikinci çağrı, ilkinin
	 * başlattığı gezinmeyi yarıda kesip döngü kurabiliyordu.
	 */
	function geriDus() {
		if (dustu) { return; }
		dustu = true;

		var u = new URL(window.location.href);
		u.searchParams.set('nb2', '1');
		window.location.replace(u.toString());
	}

	/**
	 * KAYNAK DENETİMİ — `e.origin` bakılmadan hiçbir mesaj kabul edilmiyor.
	 *
	 * Denetim olmasaydı herhangi bir pencere `{fsp:1,tip:'zaman',konum:5}`
	 * yollayıp iki şeyi birden yapabilirdi: geri düşmeyi susturmak (video hiç
	 * açılmasa da) ve oynatma olmadan izlenme saydırmak.
	 */
	function bizden(e) { return e.origin === KOKEN; }

	window.addEventListener('message', function (e) {
		if (!bizden(e)) { return; }

		var m = e.data;
		if (!m || m.fsp !== 1) { return; }

		/**
		 * "BU KİMLİK YOK" — `haber` İŞARETLENMEDEN ÖNCE ele alınıyor.
		 *
		 * Sıra kritik: aşağıdaki `haber = true` satırı 12 saniyelik geri düşmeyi
		 * İPTAL ediyor. Bu dal ondan sonra gelseydi, ölü bir kimlik geri düşmeyi
		 * susturur ve izleyici "Not Found" ekranında kalıcı olarak takılırdı —
		 * yani düzeltme, düzeltmeye çalıştığı hatayı kalıcı hale getirirdi.
		 *
		 * Kaynağı gönderen FastPlay'in kendi 404 sayfası (bkz. FastPlay-V2
		 * core/helpers.php `notFound`) ve `bizden(e)` denetiminden geçmiş
		 * durumda, yani uydurulamıyor.
		 */
		if (m.tip === 'yok') { geriDus(); return; }

		haber = true;
		if (typeof m.durakli === 'boolean') { durakli = m.durakli; }

		/**
		 * İzlenme YALNIZ gerçekten oynayınca sayılıyor — sayfayı açıp
		 * kapatan ziyaretçi sayılmasın. Panelin kendi sayacı, düğümden
		 * oynatıldığındakiyle aynı uç.
		 */
		if (!sayildi && jeton && !m.durakli && (m.konum || 0) > 0) {
			sayildi = true;

			try {
				fetch('count.php', {
					method:  'POST',
					headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
					body:    't=' + encodeURIComponent(jeton),
					keepalive: true
				});
			} catch (err) {}
		}

		yukari(m);
	});

	/**
	 * TEMA KÖPRÜSÜ — iki protokol arasında çeviri.
	 *
	 * setfilm ailesi temaları oynatıcıyla `{stfp:1}` mesajlaşıyor (birlikte
	 * izle, zaman senkronu). FastPlay oynatıcısı ise `{fsp:1}` konuşuyor.
	 * Köprü araya girdiği için tema doğrudan oynatıcıyı göremiyor; bu çevirici
	 * olmasaydı eşleşen içerikte birlikte izle sessizce ölürdü.
	 *
	 * İki fark var, ikisi de burada kapatılıyor:
	 *   fsp `seeked`  → stfp `seek`
	 *   stfp `cevir`  → FastPlay'de yok; son duruma göre oynat/durdur
	 */
	function yukari(m) {
		if (parent === window) { return; }

		var tip = (m.tip === 'seeked') ? 'seek' : m.tip;

		try {
			parent.postMessage({
				stfp: 1, tip: tip,
				konum: m.konum || 0, sure: m.sure || 0, durakli: !!m.durakli
			}, '*');
		} catch (e) {}
	}

	function asagi(komut, deger) {
		try {
			cerceve.contentWindow.postMessage({ fsp: 1, komut: komut, deger: deger }, KOKEN);
		} catch (e) {}
	}

	window.addEventListener('message', function (e) {
		/**
		 * Tema mesajları FastPlay'den DEĞİL üst pencereden geliyor; kaynağı
		 * `e.source` ile ayırt ediliyor. Aksi halde aşağı yolladığımız komut
		 * yankılanıp sonsuz döngü kurabilirdi.
		 */
		if (e.source !== parent || e.source === cerceve.contentWindow) { return; }

		var m = e.data;
		if (!m || m.stfp !== 1 || !m.komut) { return; }

		if (m.komut === 'cevir') { asagi(durakli ? 'oynat' : 'durdur'); return; }

		asagi(m.komut, m.deger);
	});

	/**
	 * GERİ DÜŞME — çerçeveden hiç haber gelmezse düğümden oynat.
	 *
	 * `onload` yeterli değil: CSP `frame-ancestors` engellediğinde de tarayıcı
	 * yükleme olayını tetikliyor ama içerik boş kalıyor. Tek güvenilir işaret
	 * oynatıcının kendi mesajı.
	 *
	 * 12 saniye: yavaş bir bağlantıda oynatıcının açılması birkaç saniye
	 * sürebiliyor; daha kısa bir süre çalışan kurulumlarda boşuna geri düşme
	 * üretirdi.
	 */
	setTimeout(function () {
		if (haber) { return; }

		geriDus();
	}, 12000);
}());
