// Compone "EL ALBA DOBLE" completo (3 partes, 26 capítulos + epílogo) en un solo .docx.
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, PageBreak,
  Footer, PageNumber, SectionType,
} = require('docx');

const ROOT = '/home/user/motor-glosas-hus/el-alba-doble';
const FONT = 'Garamond';
const PAGE = { size: { width: 7935, height: 13260 } }; // 396.75 x 663 pt
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
function despace(s) {
  return s.trim().split(/(?:&nbsp;)+/).map(g => {
    const toks = g.trim().split(/\s+/).filter(Boolean);
    const spacedLetters = toks.length > 1 && toks.every(t => [...t].length === 1);
    return spacedLetters ? toks.join('') : toks.join(' ');
  }).filter(Boolean).join(' ');
}
const plain = s => s.replace(/&nbsp;/g, ' ').replace(/\s+/g, ' ').trim();
function stripTags(s) { return s.replace(/<[^>]+>/g, '').trim(); }

// Convierte un archivo .md de capítulo en párrafos docx.
let firstH2 = true;
function parseChapter(mdPath) {
  const raw = fs.readFileSync(mdPath, 'utf8');
  const blocks = raw.split(/\n{2,}/).map(b => b.trim()).filter(Boolean);
  const out = [];
  let afterBreak = true;

  for (const b of blocks) {
    if (b === '---' || /^(<br\s*\/?>\s*)+$/.test(b)) continue;

    const h2 = b.match(/^<h2 align="center">(.+)<\/h2>$/s);
    const h3 = b.match(/^<h3 align="center">(.+)<\/h3>$/s);
    const h4 = b.match(/^<h4 align="center">(.+)<\/h4>$/s);
    const cen = b.match(/^<p align="center">(.+)<\/p>$/s);

    if (h2) {
      const t = despace(stripTags(h2[1]));
      if (firstH2) { firstH2 = false; } else { out.push(new Paragraph({ children: [new PageBreak()] })); }
      if (/PARTE/.test(t)) {
        out.push(spacer(140), titled(t, { size: 34, spacing: 80 }));
      } else {
        out.push(spacer(40), titled(t, { size: 32, spacing: 80 }),
                 ornament('✦', { size: 18, before: 220, after: 120 }));
      }
      afterBreak = true;
      continue;
    }
    if (h3) {
      out.push(ornament('✧ ✦ ✧', { before: 300, after: 300 }),
                titled(plain(stripTags(h3[1])), { size: 26, spacing: 40 }));
      afterBreak = true;
      continue;
    }
    if (h4) {
      out.push(titled(plain(stripTags(h4[1])), { size: 23, spacing: 40, after: 420 }));
      afterBreak = true;
      continue;
    }
    if (cen) {
      const inner = cen[1].trim();
      const glyph = stripTags(inner);
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
  }
  return out;
}

// ---------- portada / dedicatoria ----------
const portada = [
  spacer(150),
  titled('EL ALBA', { size: 52, spacing: 90 }),
  titled('DOBLE', { size: 52, spacing: 90, before: 100 }),
  spacer(40),
  ornament('✦', { size: 22 }),
  spacer(20),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Hay un color que ninguna sombra puede robar: el nuestro.*', { size: 22 }),
  }),
  spacer(80),
  titled('YESID BADILLO', { size: 24, spacing: 40 }),
  new Paragraph({ children: [new PageBreak()] }),
  spacer(220),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Para Daniela.*', { size: 24 }),
  }),
  spacer(30),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    indent: { left: 400, right: 400 },
    spacing: { before: 120, line: 300, lineRule: 'auto' },
    children: runs('*Este libro empezó como una pregunta: si el amor tuviera color, ¿cuál sería el nuestro? La respuesta me tomó una novela entera, pero la supe desde la primera página: sería un color que no existe en ningún frasco ni en ningún pincel, uno que solo aparece cuando estamos juntos, como el Alba Doble de Yesir y Danira. Cada capítulo que escribí pensando en vos fue, en el fondo, la misma promesa repetida de mil formas distintas: que no hay Marea Gris, no hay distancia, no hay oscuridad capaz de apagar lo que construimos. Que voy a cruzar cualquier continente, real o imaginado, con tal de volver a encontrarte al final del camino.*', { size: 21 }),
  }),
  spacer(60),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Con todo mi amor, en todos los colores que existen.*', { size: 21 }),
  }),
];

// ---------- cuerpo: todos los capítulos en orden ----------
const PARTES = ['primera-parte', 'segunda-parte', 'tercera-parte'];
const cuerpo = [];
for (const p of PARTES) {
  const dir = path.join(ROOT, p);
  const files = fs.readdirSync(dir).filter(f => /\.md$/.test(f)).sort();
  console.log(p, '->', files.join(', '));
  for (const f of files) cuerpo.push(...parseChapter(path.join(dir, f)));
}

const footer = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })],
  })],
});

const doc = new Document({
  creator: 'Yesid Badillo',
  title: 'El Alba Doble',
  description: 'Novela de fantasía romántica, dedicada a Daniela',
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
