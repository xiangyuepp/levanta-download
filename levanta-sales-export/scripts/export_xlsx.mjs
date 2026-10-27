import fs from 'node:fs/promises';
import path from 'node:path';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';

const [input,output]=process.argv.slice(2);
if(!input||!output)throw new Error('Usage: node export_xlsx.mjs sales.json sales.xlsx');
const data=JSON.parse(await fs.readFile(input,'utf8'));
const expected=['Marketplace Program','Date','Creator','Clicks','Conversions','Sales','Commission'];
if(JSON.stringify(data.headers)!==JSON.stringify(expected)||!Array.isArray(data.rows))throw new Error('Invalid seven-column source');
const rows=data.rows.map(r=>{
  if(!Array.isArray(r)||r.length!==7)throw new Error('Invalid row');
  const date=new Date(r[1]+'T00:00:00Z');
  if(!Number.isFinite(date.getTime())||![3,4,5,6].every(i=>r[i]!==null&&r[i]!==''&&Number.isFinite(Number(r[i]))))throw new Error('Invalid date or metric');
  const literal=v=>typeof v==='string'&&v.startsWith('=')?"'"+v:v;
  return [literal(r[0]),date,literal(r[2]),Number(r[3]),Number(r[4]),Number(r[5]),Number(r[6])];
});
const wb=Workbook.create();
const s=wb.worksheets.add('Sales Records');
s.showGridLines=false;
s.getRange('A1:G1').values=[expected];
if(rows.length)s.getRange(`A2:G${rows.length+1}`).values=rows;
if(rows.length){const t=s.tables.add(`A1:G${rows.length+1}`,true,'SalesRecords');t.showFilterButton=true;}
const last=Math.max(1,rows.length+1);
s.getRange(`A1:G${last}`).format.font={name:'Arial',size:11,color:'#263238'};
s.getRange(`A1:G${last}`).format.verticalAlignment='center';
s.getRange(`A1:G${last}`).format.rowHeight=28;
s.getRange('A1:G1').format={fill:'#235548',font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',rowHeight:32};
for(const [c,w] of [['A',34],['B',18],['C',42],['D',16],['E',18],['F',20],['G',20]])s.getRange(`${c}1:${c}${last}`).format.columnWidth=w;
if(rows.length){
  s.getRange(`B2:B${last}`).setNumberFormat('yyyy-mm-dd');
  s.getRange(`D2:E${last}`).setNumberFormat('#,##0');
  s.getRange(`F2:G${last}`).setNumberFormat('#,##0.00');
  s.getRange(`A2:A${last}`).format.wrapText=true;
  s.getRange(`C2:C${last}`).format.wrapText=true;
  s.getRange(`A2:G${last}`).format.autofitRows();
}
s.freezePanes.freezeRows(1);
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:`'Sales Records'!A1:G${Math.min(last,8)}`,include:'values',tableMaxRows:8,tableMaxCols:7,maxChars:1500})).ndjson);
await fs.mkdir(path.dirname(path.resolve(output)),{recursive:true});
const preview=await wb.render({sheetName:'Sales Records',range:`A1:G${Math.min(last,15)}`,scale:1.5,format:'png'});
await fs.writeFile(output+'.preview.png',new Uint8Array(await preview.arrayBuffer()));
await(await SpreadsheetFile.exportXlsx(wb)).save(output);
console.log(JSON.stringify({output,rows:rows.length,currency:'USD',timezone:'UTC'}));
