# Memory

Memory project ini ada di `~/.claude/projects/-home-pinguinstar-Projects-project-lab-p-lab/memory/`, dengan indeks `MEMORY.md` (dimuat otomatis saat sesi mulai).

## Recall — sebelum merespons
Baca memory yang relevan kalau pesan menyangkut keputusan atau preferensi sebelumnya, environment mesin, status project, atau "terakhir kali / kita sudah sepakat". Pilih berdasarkan deskripsi di MEMORY.md; jangan muat semuanya. Lewati kalau topiknya sudah lengkap di konteks.

## Remember — setelah respons yang substantif
1. Ada arahan user (preferensi, koreksi, "ingat ini"), kesimpulan non-trivial, atau fakta yang awet? Kalau tidak, berhenti.
2. Sudah ada memory yang tumpang tindih? Tambah informasi → perbarui. Bertentangan → ganti. Tidak ada → buat file baru.
3. Layak disimpan? Simpan konteks khusus user atau sintesis lintas sumber. Jangan simpan yang bisa ditemukan dengan sekali cari.

## Format
Satu memory per file, nama kebab-case:

```markdown
---
name: kebab-case-slug
description: ringkasan satu baris untuk pencocokan relevansi
metadata:
  type: user | feedback | project | reference
---

Isi. Untuk feedback/project tambahkan:
**Why:** alasannya
**How to apply:** kapan ini berlaku
```

Tautkan memory terkait dengan `[[slug]]`. Ubah tanggal relatif ("kemarin") menjadi tanggal absolut. Setelah membuat atau mengubah file, perbarui satu baris di `MEMORY.md` (maks. 200 baris).

## Jangan disimpan
- Struktur kode atau pola yang bisa dibaca dari repo
- Status yang sudah tercatat di `rencana.md` (cukup rujuk file itu)
- Solusi debugging (fix-nya ada di kode)
- Detail tugas yang hanya berguna di sesi ini
- Secret, API key, token
