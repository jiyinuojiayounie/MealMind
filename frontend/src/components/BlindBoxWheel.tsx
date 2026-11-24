const decorations = ['🥬', '🍜', '🍅', '🍚', '🥕', '🍳', '🍄', '🥟']
const colors = ['#e9ad78', '#f4d48a', '#c7d6a5', '#8fbca1', '#f2bbac', '#ebcf99', '#dae5b7', '#e9b48f']
const slice = 360 / decorations.length
const background = `conic-gradient(${colors.map((color, index) =>
  `${color} ${index * slice}deg ${(index + 1) * slice}deg`,
).join(',')})`

export function BlindBoxWheel({ rotation, spinning }: { rotation: number; spinning: boolean }) {
  return (
    <div className="blind-wheel" aria-hidden="true">
      <div className={`blind-wheel-disc${spinning ? ' is-spinning' : ''}`}
        style={{ background, transform: `rotate(${rotation}deg)` }}>
        {decorations.map((icon, index) => {
          const angle = (index + 0.5) * slice
          return (
            <div key={icon} className="blind-wheel-spoke" style={{ transform: `rotate(${angle}deg)` }}>
              <span style={{ transform: `rotate(${-angle}deg)` }}>{icon}</span>
            </div>
          )
        })}
      </div>
      <div className="blind-wheel-hub">✦</div>
    </div>
  )
}
