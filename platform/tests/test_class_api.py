"""Halaman guru gaya kelas (class_api.py): progres, detail siswa, laporan sesi, export CSV.

Memakai ServerCase dari test_auth.py: alice punya satu sesi bernilai (SCORED) di
net-001, bob hanya sesi live, dan akun admin1 / guru1 ikut ada di DB.
"""

import csv
import io

from test_auth import PASSWORD, SCORED, Client, ServerCase   # noqa: F401  (ServerCase: basis kelas test)

import server  # noqa: E402

GOLDEN_SESSION = "20261103-010646"   # golden/ net-001 yang sudah dinilai (bukan sessions/ alice)


class TestClassApi(ServerCase):
    style = "kelas"

    def test_only_staff_and_style_and_login(self):
        self.assertEqual(Client().get("/api/class/progress").status, 401)
        self.assertEqual(self.logged_in("guru1").get("/api/class/progress").status, 200)
        self.assertEqual(self.logged_in("admin1").get("/api/class/progress").status, 200)
        self.assertEqual(self.logged_in("alice").get("/api/class/progress").status, 403)
        self.assertEqual(self.logged_in("alice").get("/api/class/export.csv").status, 403)

    def test_progress(self):
        data = self.logged_in("guru1").get("/api/class/progress").json()
        self.assertEqual(data["labs"], [{"id": "net-001", "title": data["labs"][0]["title"]}])
        students = {s["username"]: s for s in data["students"]}
        self.assertTrue({"alice", "bob"} <= set(students))
        self.assertNotIn("admin1", students)
        self.assertNotIn("guru1", students)

        rows = server.user_sessions("alice")
        self.assertEqual(len(rows), 1)
        alice = students["alice"]
        self.assertEqual(alice["sessions"], 1)
        self.assertEqual(alice["points"], server.points(rows))
        self.assertEqual(alice["best_scores"], {"net-001": rows[0]["final_score"]})
        self.assertEqual(alice["attempts"], {"net-001": 1})
        self.assertEqual(alice["last_session"], rows[0]["date"])

        bob = students["bob"]
        self.assertEqual((bob["sessions"], bob["points"]), (0, 0))
        self.assertEqual((bob["best_scores"], bob["attempts"], bob["last_session"]), ({}, {}, None))

    def test_inactive_student_hidden(self):
        self.store.create_user("dina", PASSWORD, "siswa", "Dina D")
        self.addCleanup(self.store.delete_user, "dina")
        self.store.set_active("dina", False)
        students = {s["username"] for s in self.logged_in("guru1").get("/api/class/progress").json()["students"]}
        self.assertNotIn("dina", students)
        self.assertEqual(self.logged_in("guru1").get("/api/class/students/dina").status, 404)

    def test_student_detail(self):
        response = self.logged_in("guru1").get("/api/class/students/alice")
        self.assertEqual(response.status, 200)
        data = response.json()
        self.assertEqual(data["student"], {"username": "alice", "display_name": "Alice A", "role": "siswa"})
        self.assertEqual(len(data["sessions"]), 1)
        self.assertEqual(data["sessions"][0]["session"], SCORED)
        self.assertEqual(data["points"], server.points(server.user_sessions("alice")))

    def test_student_detail_not_found(self):
        guru = self.logged_in("guru1")
        for username in ("guru1", "admin1", "tidakada", "Alice!", "local"):
            response = guru.get(f"/api/class/students/{username}")
            self.assertEqual(response.status, 404, username)
            self.assertEqual(response.json()["detail"], "Siswa tidak ditemukan.")

    def test_session_report(self):
        guru = self.logged_in("guru1")
        response = guru.get(f"/api/class/students/alice/labs/net-001/sessions/{SCORED}")
        self.assertEqual(response.status, 200)
        self.assertIn("result", response.json())
        self.assertEqual(guru.get(f"/api/class/students/bob/labs/net-001/sessions/{SCORED}").status, 404)
        self.assertEqual(guru.get("/api/class/students/alice/labs/tidak-ada/sessions/" + SCORED).status, 404)

    def test_golden_session_not_served(self):
        guru = self.logged_in("guru1")
        # Sesi golden punya evaluation.json, tapi endpoint ini hanya melihat sessions/ milik siswa.
        self.assertEqual(guru.get(f"/api/class/students/alice/labs/net-001/sessions/{GOLDEN_SESSION}").status, 404)
        # Sanity: lewat endpoint sesi biasa (guru, golden=True) sesi itu memang ada.
        self.assertEqual(guru.get(f"/api/labs/net-001/sessions/{GOLDEN_SESSION}").status, 200)

    def test_export_csv(self):
        response = self.logged_in("guru1").get("/api/class/export.csv")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.header("content-type"), ["text/csv; charset=utf-8"])
        self.assertEqual(response.header("content-disposition"), ['attachment; filename="nilai-kelas.csv"'])
        self.assertTrue(response.body.startswith("\ufeff".encode()))   # BOM untuk Excel
        table = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
        self.assertEqual(table[0], ["username", "nama", "poin", "sesi", "net-001"])
        rows = {r[0]: r for r in table[1:]}
        self.assertNotIn("admin1", rows)
        self.assertNotIn("guru1", rows)
        session_rows = server.user_sessions("alice")
        expected_score = str(round(session_rows[0]["final_score"]))
        self.assertEqual(rows["alice"], ["alice", "Alice A", str(server.points(session_rows)), "1", expected_score])
        self.assertEqual(rows["bob"], ["bob", "Bob B", "0", "0", ""])

    def test_export_csv_escapes_formula_cells(self):
        self.store.create_user("mallory", PASSWORD, "siswa", "=1+1")
        self.addCleanup(self.store.delete_user, "mallory")
        response = self.logged_in("guru1").get("/api/class/export.csv")
        table = list(csv.reader(io.StringIO(response.body.decode("utf-8-sig"))))
        mallory = [r for r in table if r and r[0] == "mallory"]
        self.assertEqual(len(mallory), 1)
        self.assertEqual(mallory[0][1], "'=1+1")
        self.assertEqual(mallory[0][2], "0")   # angka tidak diberi awalan


class TestClassApiMandiri(ServerCase):
    """Gaya mandiri: semua halaman guru 404, termasuk untuk guru dan admin."""

    style = "mandiri"

    def test_hidden_in_mandiri_style(self):
        for username in ("guru1", "admin1"):
            client = self.logged_in(username)
            for path in ("/api/class/progress", "/api/class/students/alice",
                         f"/api/class/students/alice/labs/net-001/sessions/{SCORED}", "/api/class/export.csv"):
                self.assertEqual(client.get(path).status, 404, (username, path))
        self.assertEqual(Client().get("/api/class/progress").status, 401)
