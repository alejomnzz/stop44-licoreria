// Dibujos de los productos según la categoría. Se usan mientras el producto
// no tenga foto real (las fotos llegan en el paso de Inventario).

const COLORES = {
  Aguardiente: ["#2f8f5b", "#d21f2b"],
  Ron: ["#a8561c", "#e9c46a"],
  Whisky: ["#6b3b12", "#f1e6c8"],
  Cerveza: ["#7a4a12", "#d21f2b"],
  Vino: ["#6d1a2e", "#efe2c4"],
  Vodka: ["#dfe9f0", "#1c3f94"],
  Tequila: ["#e8c766", "#2b5d3a"],
  Ginebra: ["#cfe8e0", "#1d5c63"],
  "Gaseosas y aguas": ["#d21f2b", "#ffffff"],
  Energizantes: ["#1c1c1c", "#9be15d"],
  Snacks: ["#f2b33d", "#d21f2b"],
  Cigarrillos: ["#ffffff", "#d21f2b"],
  Hielo: ["#9fd8f0", "#ffffff"],
  Otros: ["#bdbdb6", "#000000"],
};

const borde = 'stroke="#000" stroke-width="2.5" stroke-linejoin="round"';

function botella(c, t, corta = false) {
  const y = corta ? 8 : 2, alto = corta ? 6 : 8, cuello = corta ? 14 : 10, largo = corta ? 12 : 14, hombro = corta ? 44 : 42;
  return `<rect x="25" y="${y}" width="10" height="${alto}" rx="2" fill="${t}" ${borde}/>
    <path d="M26 ${cuello}h8v${largo}c8 4 12 9 12 18v30a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4V${hombro}c0-9 4-14 12-18z" fill="${c}" ${borde}/>
    <rect x="16" y="46" width="28" height="16" rx="2" fill="${t}"/>`;
}

const FORMAS = {
  Aguardiente: botella, Ron: botella, Vodka: botella, Tequila: botella, Ginebra: botella,
  Vino: (c, t) => `<rect x="26" y="2" width="8" height="16" rx="2" fill="#111"/>
    <path d="M26 18h8v8c6 3 10 8 10 15v31a4 4 0 0 1-4 4H20a4 4 0 0 1-4-4V41c0-7 4-12 10-15z" fill="${c}" ${borde}/>
    <rect x="18" y="46" width="24" height="16" rx="2" fill="${t}"/>`,
  Whisky: (c, t) => `<rect x="25" y="4" width="10" height="12" rx="2" fill="#111"/>
    <rect x="14" y="16" width="32" height="58" rx="5" fill="${c}" ${borde}/>
    <rect x="18" y="34" width="24" height="20" rx="2" fill="${t}"/>`,
  Cerveza: (c, t) => botella(c, t, true),
  "Gaseosas y aguas": (c, t) => `<rect x="16" y="10" width="28" height="62" rx="6" fill="${c}" ${borde}/>
    <rect x="18" y="6" width="24" height="6" rx="3" fill="#bbb" ${borde}/>
    <rect x="16" y="30" width="28" height="18" fill="${t}"/>`,
  Energizantes: (c, t) => `<rect x="19" y="8" width="22" height="66" rx="5" fill="${c}" ${borde}/>
    <path d="M27 24l-4 16h7l-3 16 9-20h-7l4-12z" fill="${t}"/>`,
  Snacks: (c, t) => `<path d="M12 14l6-6h24l6 6-3 58H15z" fill="${c}" ${borde}/>
    <circle cx="30" cy="42" r="10" fill="${t}"/>`,
  Cigarrillos: (c, t) => `<rect x="14" y="14" width="32" height="56" rx="3" fill="${c}" ${borde}/>
    <rect x="14" y="14" width="32" height="16" fill="${t}"/>
    <rect x="20" y="8" width="5" height="8" fill="#f2e3c9" ${borde}/><rect x="28" y="6" width="5" height="10" fill="#f2e3c9" ${borde}/>`,
  Hielo: (c) => `<path d="M12 22h36l-3 50H15z" fill="${c}" ${borde}/>
    <rect x="19" y="38" width="10" height="10" rx="2" fill="#fff" transform="rotate(-12 24 43)"/>
    <rect x="31" y="46" width="10" height="10" rx="2" fill="#fff" transform="rotate(10 36 51)"/>
    <rect x="23" y="56" width="10" height="10" rx="2" fill="#fff"/>`,
  Otros: (c, t) => `<rect x="14" y="20" width="32" height="50" rx="4" fill="${c}" ${borde}/>
    <path d="M14 34h32" stroke="${t}" stroke-width="3"/>`,
};

export function dibujoProducto(categoria) {
  const [c, t] = COLORES[categoria] || COLORES.Otros;
  const forma = FORMAS[categoria] || FORMAS.Otros;
  return `<svg viewBox="0 0 60 80" aria-hidden="true">${forma(c, t)}</svg>`;
}
