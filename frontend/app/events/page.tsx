import { getEvents } from "@/lib/api";

export default async function EventsPage() {
  const events = await getEvents();

  return (
    <main className="grid">
      <section className="card">
        <h2 className="title-blue" style={{ marginTop: 0 }}>
          Recent Events
        </h2>
        <table>
          <thead>
            <tr>
              <th>Event Type</th>
              <th>Aggregate</th>
              <th>When</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr key={event.event_id}>
                <td className="text-blue">{event.event_type}</td>
                <td>
                  {event.aggregate_type} / {event.aggregate_id}
                </td>
                <td>{new Date(event.occurred_at).toLocaleString()}</td>
                <td className="mono">{JSON.stringify(event.details)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </main>
  );
}


