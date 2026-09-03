import { redirect } from 'next/navigation';
// OPSpilot - root page: redirect to /dashboard (see docs/STITCH_INVENTORY.md S1).
export default function HomePage() {
  redirect('/dashboard');
}
