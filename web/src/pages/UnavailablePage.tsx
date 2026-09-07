import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/EmptyState'

export function UnavailablePage({ title, description }: { title: string; description: string }) {
  return (
    <Card>
      <EmptyState variant="unavailable" title={title} description={description} />
    </Card>
  )
}
