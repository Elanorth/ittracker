# Pre-commit Hooks Kurulumu

## Ne yapar?

Her `git commit` öncesi otomatik olarak:
- **ruff** — Python lint (unused import, sıralama, syntax) + format (quote, spacing)
- **detect-secrets** — kazara `.env`'den geçen şifre/API key tespit
- **trailing-whitespace, end-of-file-fixer, check-yaml, check-merge-conflict** — temel hijyen

CI'da da (`.github/workflows/ci.yml`) aynı kontroller `pre-commit run --all-files` ile çalıştırılır. Yani lokalde unutsanız bile CI yakalar.

## Tek seferlik kurulum

```bash
# Repo kökünde:
pip install pre-commit
pre-commit install
```

Bundan sonra her `git commit` öncesi hook'lar otomatik koşar.

## Manuel çalıştırma

```bash
pre-commit run --all-files          # tüm dosyalarda
pre-commit run ruff --all-files     # sadece ruff
pre-commit run detect-secrets       # sadece staged
```

## Bypass (gerekirse — dikkatli kullan)

```bash
git commit --no-verify -m "..."     # hook'ları atla
```

Sadece acil hotfix için. CI yine de kontrol eder, PR'ı geçirmez.

## detect-secrets baseline

`.secrets.baseline` dosyası repo'da var. Bilinen "secret-gibi-görünen-ama-aslında-değil" string'leri (örn. test fixture'ları, dokümanlardaki örnekler) içerir.

**Yeni baseline oluşturmak gerekirse:**
```bash
detect-secrets scan > .secrets.baseline
git add .secrets.baseline && git commit -m "chore: baseline yenile"
```

**Bir uyarıyı manuel onaylamak (gerçekten secret değil):**
```bash
detect-secrets audit .secrets.baseline
# Interaktif: her satır için y/n
```

## ruff config

`ruff.toml`'da:
- Aktif kurallar: E9, F, I, UP, B (syntax, pyflakes, import sort, modernize, bugbear)
- Ignore: E501 (line length — 120'ye yükseltildi), F841 (kullanılmayan değişken), B008 (Flask default arg)
- Format: double quote, space indent

Daha sıkı yapmak için (öneri):
- `D` (docstring): zorunlu docstring
- `S` (bandit): güvenlik (eval, pickle, exec)
- `N` (pep8-naming): isimlendirme

Her ekleme için: `ruff check --select=NEW_RULE .` ile önce mevcut violation'ları gör, kademeli düzelt.

## Hook versiyon güncelleme

```bash
pre-commit autoupdate
```

Her 2-3 ayda bir önerilir. Hook repo'larındaki en son tag'lere geçer.
