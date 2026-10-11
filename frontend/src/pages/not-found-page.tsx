import { Link } from 'react-router'

import { Button } from '@/components/ui/button'

export function NotFoundPage() {
  return (
    <div className="flex flex-col items-start gap-4">
      <h1 className="text-2xl font-semibold">Страница не найдена</h1>
      <Button asChild variant="secondary">
        <Link to="/">На главную</Link>
      </Button>
    </div>
  )
}
