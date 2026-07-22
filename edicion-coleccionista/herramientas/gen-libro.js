// Compone el Libro I completo de la Edición Coleccionista (docx) a partir
// de los markdown editados en edicion-coleccionista/libro-i/.
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, PageBreak,
  Footer, PageNumber, SectionType,
} = require('docx');

const DIR = '/home/user/motor-glosas-hus/edicion-coleccionista/libro-i';
const FONT = 'Garamond';
const PAGE = { size: { width: 7935, height: 13260 } }; // 396.75 x 663 pt (formato del fondo)
const MARGIN = { top: 1550, bottom: 1350, left: 1280, right: 1280 };

function runs(text, base = {}) {
  const out = [];
  for (const p of text.split(/(\*[^*]+\*)/g).filter(Boolean)) {
    if (p.startsWith('*') && p.endsWith('*') && p.length > 2) {
      out.push(new TextRun({ text: p.slice(1, -1), italics: true, font: FONT, ...base }));
    } else {
      out.push(new TextRun({ text: p, font: FONT, ...base }));
    }
  }
  return out;
}

const body = (text, first) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  indent: first ? undefined : { firstLine: 400 },
  spacing: { line: 300, lineRule: 'auto', after: 0 },
  children: runs(text, { size: 22 }),
});

const ornament = (text, { before = 260, after = 260, size = 20 } = {}) => new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before, after, line: 300, lineRule: 'auto' },
  children: [new TextRun({ text, font: FONT, size })],
});

const spacer = pts => new Paragraph({ spacing: { before: pts * 20, after: 0 }, children: [] });

const titled = (text, { size, bold = false, italics = false, spacing = 0, before = 0, after = 0 }) => new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { before, after },
  children: [new TextRun({ text, font: FONT, size, bold, italics, characterSpacing: spacing })],
});

// "C A P Í T U L O&nbsp;&nbsp; I X" -> "CAPÍTULO IX"
// Los grupos de palabra están separados por &nbsp;; dentro de un grupo,
// las letras van separadas por espacios simples.
function despace(s) {
  return s.trim().split(/(?:&nbsp;)+/).map(g => {
    const toks = g.trim().split(/\s+/).filter(Boolean);
    const spacedLetters = toks.length > 1 && toks.every(t => [...t].length === 1);
    return spacedLetters ? toks.join('') : toks.join(' ');
  }).filter(Boolean).join(' ');
}

// texto normal: solo colapsar espacios/nbsp
const plain = s => s.replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();

function stripTags(s) { return s.replace(/<[^>]+>/g, '').trim(); }

// Convierte un archivo de capítulo a párrafos docx.
// firstContent: true si es el primer contenido de la sección (sin PageBreak previo)
function parseChapter(mdPath, firstContent) {
  let raw = fs.readFileSync(mdPath, 'utf8');
  // en 00-prologo.md, salta la portada: arranca en el h2 del PRÓLOGO
  const pr = raw.indexOf('<h2 align="center">P R Ó L O G O</h2>');
  if (pr >= 0) raw = raw.slice(pr);

  const blocks = raw.split(/\n{2,}/).map(b => b.trim()).filter(Boolean);
  const out = [];
  let afterBreak = true;
  let sawBody = false;

  for (const b of blocks) {
    if (b === '---' || /^(<br\s*\/?>\s*)+$/.test(b)) continue;

    const h2 = b.match(/^<h2 align="center">(.+)<\/h2>$/s);
    const h4 = b.match(/^<h4 align="center">(.+)<\/h4>$/s);
    const cen = b.match(/^<p align="center">(.+)<\/p>$/s);

    if (h2) {
      const t = despace(stripTags(h2[1]));
      if (/LIBRO/.test(t)) continue; // portada del libro: la arma el main
      if (!firstContent || out.length) out.push(new Paragraph({ children: [new PageBreak()] }));
      if (/PARTE/.test(t)) {
        out.push(spacer(140), titled(t, { size: 30, spacing: 80 }));
        // la parte vive en su propia página; el capítulo siguiente hará su PageBreak
      } else {
        out.push(spacer(40), titled(t, { size: 32, spacing: 80 }),
                 ornament('✦', { size: 18, before: 220, after: 120 }));
      }
      afterBreak = true;
      continue;
    }
    if (h4) {
      out.push(titled(plain(stripTags(h4[1])), { size: 23, spacing: 40, after: 420 }));
      afterBreak = true;
      continue;
    }
    if (b.startsWith('<h1') || b.startsWith('<h3') || b.startsWith('>')) continue;
    if (cen) {
      const inner = cen[1].trim();
      const glyph = stripTags(inner);
      if (glyph === '✧ ✦ ✧') continue; // adorno de cierre por archivo: se pone uno global al final
      if (/^[✦✧\s❦]+$/.test(glyph)) { out.push(ornament(glyph)); afterBreak = true; continue; }
      if (/<em>/.test(inner)) {
        out.push(new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { before: 160, after: 160 },
          children: [new TextRun({ text: glyph, font: FONT, size: 22, italics: true })],
        }));
      } else {
        out.push(titled(glyph, { size: 24, spacing: 40, before: 300, after: 120 }));
      }
      afterBreak = true;
      continue;
    }
    out.push(body(b.replace(/\n/g, ' '), afterBreak));
    afterBreak = false;
    sawBody = true;
  }
  if (!sawBody) throw new Error(`sin cuerpo: ${mdPath}`);
  return out;
}


// ---------- dedicatoria personal ----------
const DED_TEXTOS = [
  ['c', 'A Daniela, mi compañera de vida.'],
  ['j', 'Gracias por caminar a mi lado cuando el sendero fue claro y también cuando la niebla parecía esconder el horizonte. Gracias por creer en mí incluso en los días en que yo olvidaba cómo hacerlo. En cada una de estas páginas hay noches que me regalaste, silencios que respetaste, sueños que protegiste y un amor que hizo posible que esta historia existiera.'],
  ['c', 'Y a Dania, mi pequeña estrella.'],
  ['j', 'Llegaste para enseñarme que el universo más inmenso no está sobre nuestras cabezas, sino entre los brazos de un padre y la sonrisa de una hija. Desde que naciste comprendí que todas las constelaciones del cielo son apenas un reflejo de la luz que llevas dentro. Si algún día lees estas páginas, quiero que sepas que fueron escritas pensando en el mundo que deseo dejarte: uno donde nunca dejes de hacer preguntas, donde la curiosidad sea más fuerte que el miedo y donde tu corazón siempre encuentre el camino hacia la verdad.'],
  ['j', 'Este libro habla de héroes, de dioses, de estrellas y de hombres que buscaron comprender el firmamento. Pero la verdad es que los dos mayores milagros de mi vida nunca estuvieron en el cielo.'],
  ['c', 'Siempre estuvieron esperándome en casa.'],
  ['j', 'Porque entendí que no hay gloria más grande que regresar al lugar donde ustedes están; no hay conquista comparable con escuchar sus voces; no hay eternidad más hermosa que el tiempo compartido a su lado.'],
  ['j', 'Si alguna vez este libro encuentra un lugar en las manos de otros lectores, deseo que sepan que antes de pertenecerles a ellos, siempre les perteneció a ustedes.'],
  ['c', 'Cada palabra nació de mi amor por ustedes.'],
  ['c', 'Cada página fue escrita pensando en ustedes.'],
  ['c', 'Cada sueño que este libro alcance será, para siempre, de ustedes.'],
  ['c', 'Con todo mi amor, hoy y siempre.'],
];

function dedicatoria() {
  const out = [spacer(30), ornament('✦', { size: 20, after: 300 })];
  for (const [modo, texto] of DED_TEXTOS) {
    out.push(new Paragraph({
      alignment: modo === 'c' ? AlignmentType.CENTER : AlignmentType.JUSTIFIED,
      indent: modo === 'j' ? { left: 280, right: 280 } : undefined,
      spacing: { before: modo === 'c' ? 260 : 160, after: modo === 'c' ? 160 : 0, line: 300, lineRule: 'auto' },
      children: runs('*' + texto + '*', { size: 22 }),
    }));
  }
  out.push(ornament('✦', { size: 20, before: 300 }));
  return out;
}

// ---------- portada / frontmatter ----------
const portada = [
  spacer(130),
  titled('HIJOS', { size: 56, spacing: 90 }),
  titled('del', { size: 30, italics: true, before: 160, after: 160 }),
  titled('FIRMAMENTO', { size: 56, spacing: 90 }),
  spacer(30),
  ornament('✦', { size: 22 }),
  spacer(20),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Una épica de grandes almas, mitología viva y el amor que lo recuerda todo*', { size: 23 }),
  }),
  spacer(60),
  titled('YESID PÉREZ BADILLO', { size: 24, spacing: 40 }),
  new Paragraph({ children: [new PageBreak()] }),
  spacer(200),
  new Paragraph({ alignment: AlignmentType.CENTER, children: runs('*A los que no supieron.*', { size: 23 }) }),
  new Paragraph({ children: [new PageBreak()] }),
  ...dedicatoria(),
  new Paragraph({ children: [new PageBreak()] }),
  spacer(120),
  titled('LIBRO I', { size: 34, spacing: 80 }),
  ornament('✧ ✦ ✧', { before: 300, after: 300 }),
  titled('LAS VOCES QUE NACIERON DEL FUEGO', { size: 26, spacing: 40 }),
];

// ---------- cuerpo: todos los capítulos en orden ----------
const files = fs.readdirSync(DIR).filter(f => /^\d\d-.*\.md$/.test(f)).sort();
console.log('componiendo:', files.join(', '));
const cuerpo = [];
files.forEach((f, i) => cuerpo.push(...parseChapter(path.join(DIR, f), i === 0)));
cuerpo.push(ornament('✧ ✦ ✧', { before: 260, after: 0 }));

const footer = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })],
  })],
});

const doc = new Document({
  creator: 'Yesid Pérez Badillo',
  title: 'Hijos del Firmamento — Libro I: Las Voces Que Nacieron Del Fuego',
  description: 'Edición Coleccionista',
  styles: { default: { document: { run: { font: FONT, size: 22 } } } },
  sections: [
    {
      properties: { page: { ...PAGE, margin: MARGIN } },
      footers: { default: new Footer({ children: [new Paragraph({ children: [] })] }) },
      children: portada,
    },
    {
      properties: {
        type: SectionType.NEXT_PAGE,
        page: { ...PAGE, margin: MARGIN, pageNumbers: { start: 1 } },
      },
      footers: { default: footer },
      children: cuerpo,
    },
  ],
});

const OUT = process.argv[2];
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log('written', OUT, buf.length, 'bytes');
});
