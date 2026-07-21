type PlaceholderPageProps = {
  title: string
  description: string
}

export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <section className="page-card">
      <p className="eyebrow">功能页面预留</p>
      <h2>{title}</h2>
      <p>{description}</p>
      <div className="empty-panel">
        该页面已完成路由占位，后续开发会接入真实接口和业务组件。
      </div>
    </section>
  )
}
