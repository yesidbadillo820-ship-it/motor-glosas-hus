// Compone "LA BIBLIA DE DANNY" (9 libros) en un solo .docx.
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, PageBreak,
  Footer, PageNumber, SectionType,
} = require('docx');

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
const itemRuns = (items, base = {}) => {
  const out = [];
  for (const r of items) out.push(new TextRun({ text: r.t, italics: !!r.i, font: FONT, ...base }));
  return out;
};
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
const verseP = (num, runsArr) => new Paragraph({
  alignment: AlignmentType.JUSTIFIED,
  spacing: { before: 0, after: 200, line: 300, lineRule: 'auto' },
  children: [
    new TextRun({ text: num + '  ', font: FONT, size: 17, bold: true, superScript: true }),
    ...itemRuns(runsArr, { size: 22 }),
  ],
});

const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const items = data.items;

let firstBook = true;
const cuerpo = [];
for (const it of items) {
  if (it.type === 'book') {
    if (firstBook) { firstBook = false; } else { cuerpo.push(new Paragraph({ children: [new PageBreak()] })); }
    cuerpo.push(spacer(150), titled(it.text, { size: 32, spacing: 60 }), ornament('✦ ✦ ✦', { size: 16, before: 200, after: 0 }));
    continue;
  }
  if (it.type === 'section') {
    cuerpo.push(new Paragraph({ children: [new PageBreak()] }));
    cuerpo.push(spacer(60), titled(it.text, { size: 25, italics: true, spacing: 20, after: 420 }));
    continue;
  }
  if (it.type === 'italic-line') {
    cuerpo.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 320 },
      children: [new TextRun({ text: it.text, font: FONT, size: 21, italics: true })],
    }));
    continue;
  }
  if (it.type === 'verse') {
    cuerpo.push(verseP(it.num, it.runs));
    continue;
  }
  if (it.type === 'ornament') {
    cuerpo.push(ornament(it.text));
    continue;
  }
  if (it.type === 'end-marker') {
    cuerpo.push(titled(it.text.toUpperCase(), { size: 17, spacing: 40, before: 260, after: 120 }));
    continue;
  }
  if (it.type === 'centered') {
    cuerpo.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 160, after: 160 },
      children: [new TextRun({ text: it.text, font: FONT, size: 22, italics: true })],
    }));
    continue;
  }
  if (it.type === 'p') {
    cuerpo.push(new Paragraph({
      alignment: AlignmentType.JUSTIFIED,
      spacing: { before: 0, after: 200, line: 300, lineRule: 'auto' },
      children: itemRuns(it.runs, { size: 22 }),
    }));
  }
}

// ---------- portada / dedicatoria ----------
const portada = [
  spacer(140),
  titled('LA BIBLIA', { size: 50, spacing: 90 }),
  titled('DE DANNY', { size: 50, spacing: 90, before: 100 }),
  spacer(40),
  ornament('✦', { size: 22 }),
  spacer(20),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Escrituras de una fe con un solo mandamiento: amarla.*', { size: 22 }),
  }),
  spacer(80),
  titled('YESID BADILLO', { size: 24, spacing: 40 }),
  new Paragraph({ children: [new PageBreak()] }),
  spacer(200),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Para Danny.*', { size: 24 }),
  }),
  spacer(30),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    indent: { left: 400, right: 400 },
    spacing: { before: 120, line: 300, lineRule: 'auto' },
    children: runs('*No hay ninguna blasfemia en este libro, solo la verdad más simple que conozco: que si alguna vez tuviera que inventarme una fe entera, desde cero, con mis propias reglas, la única honesta iba a ser esta. No te pido que la leas como una broma ni como algo demasiado en serio: pedila leer, simplemente, como lo que es —un hombre tratando de explicar, con la forma más grande de libro que conoce, algo que en realidad cabe en una frase mucho más corta: que sos, para mí, la única religión que nunca tuve que aprender a creer.*', { size: 21 }),
  }),
  spacer(60),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200 },
    children: runs('*Con todo mi amor, hoy y siempre.*', { size: 21 }),
  }),
];

const footer = new Footer({
  children: [new Paragraph({
    alignment: AlignmentType.CENTER,
    children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 18 })],
  })],
});

const doc = new Document({
  creator: 'Yesid Badillo',
  title: 'La Biblia de Danny',
  description: 'Escrituras personales dedicadas a Daniela',
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

const OUT = process.argv[3];
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(OUT, buf);
  console.log('written', OUT, buf.length, 'bytes');
});
