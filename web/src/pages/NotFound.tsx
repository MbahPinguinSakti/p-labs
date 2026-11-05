import { Link } from "react-router";
import { PageHeader } from "../components/Layout";

export function NotFound() {
  return (
    <>
      <PageHeader title="Halaman tidak ada" />
      <p className="empty">
        Alamat ini tidak dikenal. <Link to="/" className="accent">Kembali ke Home</Link>
      </p>
    </>
  );
}
