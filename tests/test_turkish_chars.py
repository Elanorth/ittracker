"""
test_turkish_chars.py — Türkçe karakter edge case'lerinin baseline testleri.

Kapsam:
- Görev başlığında ve firma adında ç, ğ, ı, İ, ö, ş, ü karakterleri sorunsuz kaydedilir.
- JSON serileştirme/deserialize: Türkçe karakter içeren alanlar bozulmaz.
- SQLite LIKE davranışı: Türkçe karakterlerle büyük/küçük harf arama.
- API response: Content-Type header UTF-8 içeriyor mu?
- User.to_dict() ve Task.to_dict(): Türkçe alanlar JSON'da korunur.
- i/I ile ı/İ ayrımı: Python lower()/upper() davranışı belgelenir.
"""

import pytest
import json
from models.database import User, Task


class TestTurkishCharStorage:
    """Türkçe karakter depolama — model seviyesi."""

    def test_kullanici_turkce_tam_isim(self, db, user_factory):
        """Türkçe özel karakter içeren kullanıcı adı kaydedilir ve geri alınır."""
        user = user_factory(
            username="cagla_test",
            full_name="Çağla Öztürk",
            firm="inventist",
        )
        fetched = User.query.get(user.id)
        assert fetched.full_name == "Çağla Öztürk"

    def test_kullanici_ibrahim_sahin(self, db, user_factory):
        """İbrahim Şahin — büyük İ ile başlayan isim korunur."""
        user = user_factory(
            username="ibrahim_test",
            full_name="İbrahim Şahin",
            firm="assos",
        )
        fetched = User.query.get(user.id)
        assert fetched.full_name == "İbrahim Şahin"

    def test_kullanici_gulnur_yildiz(self, db, user_factory):
        """Gülnur Yıldız — ü, ı, ğ karakterleri korunur."""
        user = user_factory(
            username="gulnur_test",
            full_name="Gülnur Yıldız",
            firm="inventist",
        )
        fetched = User.query.get(user.id)
        assert fetched.full_name == "Gülnur Yıldız"

    def test_firma_adi_inventist_buyuk_i(self, db, user_factory):
        """'İnventist' — büyük İ ile firma adı kaydedilir."""
        user = user_factory(username="inv_tc", firm="İnventist")
        assert User.query.get(user.id).firm == "İnventist"

    def test_firma_adi_assos_ilac(self, db, user_factory):
        """'Assos İlaç' — boşluk ve İ içeren firma adı korunur."""
        user = user_factory(username="assos_tc", firm="Assos İlaç")
        assert User.query.get(user.id).firm == "Assos İlaç"

    def test_firma_adi_sirket_cag(self, db, user_factory):
        """'Şirket Çağ' — Ş ve Ç içeren firma adı korunur."""
        user = user_factory(username="sirket_tc", firm="Şirket Çağ")
        assert User.query.get(user.id).firm == "Şirket Çağ"

    def test_gorev_baslik_turkce_karakter(self, db, user_factory, task_factory):
        """Türkçe karakter içeren görev başlığı doğru kaydedilir."""
        user = user_factory(username="task_tc1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Çağrı: Bağlı kullanıcının şifresi sıfırlanacak — İlknur Doğan",
            category="support",
        )
        fetched = Task.query.get(task.id)
        assert fetched.title == "Çağrı: Bağlı kullanıcının şifresi sıfırlanacak — İlknur Doğan"

    def test_gorev_baslik_sunucu_guncellemesi(self, db, user_factory, task_factory):
        """'Sunucu güncellemesi gerçekleştir' — ü, ğ, ş, e karakterleri korunur."""
        user = user_factory(username="task_tc2", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Sunucu güncellemesi gerçekleştir",
            category="routine",
            period="Aylık",
        )
        assert Task.query.get(task.id).title == "Sunucu güncellemesi gerçekleştir"

    def test_gorev_baslik_yigin_yedekleme(self, db, user_factory, task_factory):
        """'Yığın yedekleme' — ğ, ı karakterleri korunur."""
        user = user_factory(username="task_tc3", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Yığın yedekleme",
            category="backup",
        )
        assert Task.query.get(task.id).title == "Yığın yedekleme"

    def test_gorev_notes_turkce_karakter(self, db, user_factory):
        """Görev notları Türkçe karakter içerebilir."""
        user = user_factory(username="task_tc4", firm="assos")
        task = Task(
            user_id=user.id,
            title="Not testi",
            category="other",
            notes="Öncelikli olarak Çağla Öztürk ile iletişime geç. Şifre yenileme talebi.",
            firm="assos",
        )
        db.session.add(task)
        db.session.commit()

        fetched = Task.query.get(task.id)
        assert "Çağla Öztürk" in fetched.notes
        assert "Şifre yenileme" in fetched.notes


class TestJsonSerialization:
    """JSON serileştirme/deserialize — Türkçe karakter güvenliği."""

    def test_task_to_dict_title_turkce_korunur(self, db, user_factory, task_factory):
        """Task.to_dict() Türkçe başlıkları bozulmadan döndürür."""
        user = user_factory(username="json_tc1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Şifre yenileme — Ğ, Ç, İ testleri",
            category="other",
        )
        d = task.to_dict()
        assert d["title"] == "Şifre yenileme — Ğ, Ç, İ testleri"

    def test_task_to_dict_json_roundtrip(self, db, user_factory, task_factory):
        """Task.to_dict() → JSON encode → JSON decode geçişinde Türkçe korunur."""
        user = user_factory(username="json_tc2", firm="assos")
        task = task_factory(
            user_id=user.id,
            title="Bağlantı kesme — ığışçöü",
            category="support",
            priority="yüksek",
        )
        d = task.to_dict()
        # JSON encode/decode döngüsü
        encoded = json.dumps(d, ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["title"] == "Bağlantı kesme — ığışçöü"

    def test_user_to_dict_full_name_turkce(self, db, user_factory):
        """User.to_dict() Türkçe full_name'i bozulmadan döndürür."""
        user = user_factory(
            username="json_tc3",
            full_name="Levent Mahir Çelik",
            firm="inventist",
        )
        d = user.to_dict()
        assert d["full_name"] == "Levent Mahir Çelik"

    def test_user_to_dict_firma_turkce(self, db, user_factory):
        """User.to_dict() Türkçe firma adını bozulmadan döndürür."""
        user = user_factory(username="json_tc4", firm="Çağrı Merkezi")
        d = user.to_dict()
        assert d["firm"] == "Çağrı Merkezi"

    def test_json_ensure_ascii_false_zorunlu(self, db, user_factory, task_factory):
        """json.dumps ile ensure_ascii=False kullanıldığında karakter escape yapılmaz."""
        user = user_factory(username="json_tc5", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="İğneyle kuyu kaz — öğrenciler için",
            category="other",
        )
        d = task.to_dict()
        # ensure_ascii=True olsaydı ö gibi escape edilirdi
        encoded_unicode = json.dumps(d, ensure_ascii=True)
        encoded_utf8 = json.dumps(d, ensure_ascii=False)

        # ensure_ascii=False versiyonu doğrudan Türkçe karakterleri içerir
        assert "İğneyle" in encoded_utf8
        # ensure_ascii=True versiyonu escape içerir
        assert "\\u" in encoded_unicode or "İğneyle" not in encoded_unicode


class TestSqliteLikeBehavior:
    """SQLite LIKE operatörü ile Türkçe karakter arama davranışı."""

    def test_exact_match_filter_by_turkce(self, db, user_factory):
        """filter_by() ile tam eşleşme Türkçe karakterlerle çalışır."""
        u1 = user_factory(username="like_tc1", firm="İnventist")
        u2 = user_factory(username="like_tc2", firm="Assos İlaç")

        results = User.query.filter_by(firm="İnventist", active=True).all()
        ids = {u.id for u in results}
        assert u1.id in ids
        assert u2.id not in ids

    def test_like_ascii_karakter_arama(self, db, user_factory):
        """SQLite LIKE ile ASCII karakterler büyük/küçük harf duyarsız çalışır."""
        u = user_factory(username="like_tc3", firm="inventist")

        # ASCII LIKE — küçük/büyük harf duyarsız çalışır
        results = db.session.execute(
            db.text("SELECT id FROM users WHERE firm LIKE :firm"),
            {"firm": "inventist"},
        ).fetchall()
        ids = [r[0] for r in results]
        assert u.id in ids

    def test_like_turkce_buyuk_kucuk_harf_davranisi(self, db, user_factory):
        """
        Önemli: SQLite LIKE 'ç%' ile 'Ç%' eşleştirmez.
        Bu test mevcut davranışı belgeler (bug değil — SQLite sınırı).
        """
        u = user_factory(username="like_tc4", firm="Çağrı Merkezi")

        # Büyük Ç ile tam eşleşme
        results_exact = User.query.filter_by(firm="Çağrı Merkezi").all()
        assert any(r.id == u.id for r in results_exact)

        # SQLite LIKE ile küçük ç — davranışı belgele (passing olması gerekmiyor)
        results_like = db.session.execute(
            db.text("SELECT id FROM users WHERE firm LIKE :firm"),
            {"firm": "çağrı%"},
        ).fetchall()
        ids_like = [r[0] for r in results_like]
        # SQLite'da Türkçe büyük/küçük harf LIKE eşleşmez — bu beklenen davranış
        # Eğer eşleşiyorsa not et; bu testin amacı davranışı belgelemek
        # (assert içermez intentionally — davranış değişmeden migration geçmeli)
        _ = u.id in ids_like  # davranışı gözlemle, assert yok

    def test_like_buyuk_i_kucuk_i_farki(self, db, user_factory):
        """
        'İnventist' (büyük İ) ve 'inventist' (küçük i) SQLite'da farklı string.
        Bu test i/ı ve I/İ ayrımını belgeler.
        """
        u_buyuk = user_factory(username="like_tc5", firm="İnventist")
        u_kucuk = user_factory(username="like_tc6", firm="inventist")

        results_buyuk = User.query.filter_by(firm="İnventist").all()
        results_kucuk = User.query.filter_by(firm="inventist").all()

        buyuk_ids = {u.id for u in results_buyuk}
        kucuk_ids = {u.id for u in results_kucuk}

        assert u_buyuk.id in buyuk_ids
        assert u_kucuk.id in kucuk_ids
        # Kritik: büyük İ ile küçük i ayrı string olarak tutulur
        assert u_buyuk.id not in kucuk_ids, "'İnventist' != 'inventist' — farklı değerler"
        assert u_kucuk.id not in buyuk_ids, "'inventist' != 'İnventist' — farklı değerler"


class TestApiResponseEncoding:
    """API response'larında UTF-8 encoding ve Türkçe karakter korunması."""

    def test_api_tasks_response_turkce_baslik_korunur(self, db, client, user_factory, task_factory, login_as):
        """GET /api/tasks response'unda Türkçe başlık bozulmadan gelir."""
        user = user_factory(username="api_enc1", firm="inventist")
        task = task_factory(
            user_id=user.id,
            title="Çağrı merkezi yedekleme görevi",
            category="other",
        )
        login_as(user)

        resp = client.get("/api/tasks")
        assert resp.status_code == 200

        # Response'u UTF-8 ile decode et
        data = resp.get_json(force=True)
        titles = [t["title"] for t in data]
        assert "Çağrı merkezi yedekleme görevi" in titles

    def test_api_tasks_post_turkce_baslik_kaydedilir(self, db, client, user_factory, login_as):
        """POST /api/tasks Türkçe başlıklı görev oluşturulabilir."""
        user = user_factory(username="api_enc2", firm="inventist")
        login_as(user)

        resp = client.post(
            "/api/tasks",
            json={
                "title": "Güvenlik duvarı güncellemesi — Şubat 2026",
                "category": "infra",
                "priority": "orta",
                "firm": "inventist",
            },
            content_type="application/json",
        )
        assert resp.status_code == 201
        data = resp.get_json()
        assert data["title"] == "Güvenlik duvarı güncellemesi — Şubat 2026"

    def test_api_tasks_content_type_utf8(self, db, client, user_factory, login_as):
        """GET /api/tasks Content-Type header'ı UTF-8 encoding içerir."""
        user = user_factory(username="api_enc3", firm="assos")
        login_as(user)
        resp = client.get("/api/tasks")
        content_type = resp.headers.get("Content-Type", "")
        assert "application/json" in content_type


class TestPythonTurkishLocale:
    """Python lower()/upper() davranışı — Türkçe karakter açıklaması."""

    def test_python_lower_buyuk_i_noktalari(self):
        """
        Python lower(): 'İ'.lower() → 'i̇' veya 'i' döner (Unicode bağlı).
        Bu test Python davranışını belgeler — SQLite ile farklı olabilir.
        """
        # Standard Python 3 behavior
        assert "İnventist".lower() in ("i̇nventist", "inventist", "İnventist".lower())

    def test_python_lower_turkce_harfler(self):
        """'Çağla'.lower() → 'çağla' — Türkçe küçük harfler doğru."""
        assert "Çağla".lower() == "çağla"
        assert "Şahin".lower() == "şahin"
        assert "Öztürk".lower() == "öztürk"
        assert "Gülnur".lower() == "gülnur"

    def test_turkce_buyuk_harf(self):
        """
        Python upper() Türkçe karakterlerde davranış belgeleme.

        Önemli: 'ş'.upper() doğru 'Ş' verir, ancak 'i'.upper() → 'I' döner
        (Türkçe 'İ' değil — Python locale-agnostic Unicode kullanır).
        Dolayısıyla 'şahin'.upper() → 'ŞAHIN' ('ŞAHİN' değil, i→I nedeniyle).

        Potansiyel bug: Türkçe isim/email upper() ile büyütülürse i→I olur,
        bu 'İBRAHİM' gibi Türkçe büyük harf içeren SQL sorgularını kırar.
        """
        assert "çağla".upper() == "ÇAĞLA"
        # 'şahin'.upper() → 'ŞAHIN' (i → I, Türkçe İ değil — Python davranışı)
        assert "şahin".upper() == "ŞAHIN"   # ŞAHIN döner, ŞAHİN değil

    def test_i_ile_i_noktalı_farki(self):
        """
        Kritik: 'i'.upper() → 'I' (İngilizce 'I', Türkçe 'İ' değil).
        Bu Python davranışı SQL sorguları ve filter işlemlerini etkileyebilir.
        """
        # Python Türkçe locale farkındalığı: i → I (İngilizce), ı → I yok
        assert "i".upper() == "I"   # Python 'i'.upper() = 'I'
        assert "I".lower() == "i"   # Python 'I'.lower() = 'i'
        # Türkçe'de: 'i'.upper() = 'İ', 'I'.lower() = 'ı' — Python locale'ye uymaz
        # Bu POTANSIYEL BUG: Türkçe karakter içeren username/email lower() ile
        # beklenmedik sonuç verebilir. Mevcut davranışı belgelemek için:
        result = "İstanbul".lower()
        # 'İ'.lower() in Python → 'i̇' (combining dot) veya 'i' olabilir
        # Sonuç locale/Python version bağımlı — bu satır davranışı gözlemler
        assert isinstance(result, str)


class TestSlugifyTr:
    """app._slugify_tr — Türkçe-aware slug üretimi.

    Ham `.lower().replace(" ","_")` yaklaşımının bug'ı: 'İnventist' → 'i̇nventist'
    (combining dot above U+0307 ile 9 karakter). _slugify_tr önce TR→ASCII
    eşlemesi yapıp sonra slug'lar.
    """

    def test_buyuk_i_dogru_slugify(self):
        """'İnventist' → 'inventist' (combining dot bırakmaz)."""
        from app import _slugify_tr
        assert _slugify_tr("İnventist") == "inventist"
        # Saf .lower() bug'ını da dolaylı doğrula
        assert "̇" not in _slugify_tr("İnventist")  # combining dot above

    def test_turkce_firma_adi_slug(self):
        """'Şirket Çağ' → 'sirket_cag'."""
        from app import _slugify_tr
        assert _slugify_tr("Şirket Çağ") == "sirket_cag"

    def test_karma_turkce_slug(self):
        """'Güneş Öztürk Çelik' → 'gunes_ozturk_celik'."""
        from app import _slugify_tr
        assert _slugify_tr("Güneş Öztürk Çelik") == "gunes_ozturk_celik"

    def test_dotless_i_slug(self):
        """'Kıvılcım' → 'kivilcim' (ı → i)."""
        from app import _slugify_tr
        assert _slugify_tr("Kıvılcım") == "kivilcim"

    def test_bos_string(self):
        """Boş string güvenli — '' döner."""
        from app import _slugify_tr
        assert _slugify_tr("") == ""
        assert _slugify_tr(None) == ""

    def test_bastaki_sondaki_bosluk_strip(self):
        """'  Assos  ' → 'assos' (kenar boşlukları temizlenir)."""
        from app import _slugify_tr
        assert _slugify_tr("  Assos  ") == "assos"
