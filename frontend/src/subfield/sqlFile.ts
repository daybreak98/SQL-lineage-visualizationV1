// Match MAX_SQL_CHARS in backend/app/middleware/local_delivery.py (Unicode code points).
export const maxSqlCharacters = 64 * 1024;
const previewLimit = 512 * 1024;
export const sqlPreviewLimitLabel = '512 KiB';
export type LocalSqlFile = { name: string; text: string; bom: boolean; long: boolean };

export async function readSqlFile(file: File): Promise<LocalSqlFile> {
  if (!/\.sql$/i.test(file.name)) throw new Error('请选择扩展名为 .sql 的 UTF-8 文本文件。');
  if (file.size > previewLimit) throw new Error(`SQL 文件超过本机预览上限（${sqlPreviewLimitLabel}），未读取，也未改动草稿。`);
  const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
    const reader = new FileReader();
    const failed = () => reject(new Error('无法读取所选 SQL 文件，请重新选择。'));
    reader.onerror = failed;
    reader.onabort = failed;
    reader.onload = () => reader.result && typeof reader.result !== 'string' ? resolve(reader.result) : failed();
    reader.readAsArrayBuffer(file);
  });
  let sql: string;
  try {
    sql = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
  } catch {
    throw new Error('文件不是有效的 UTF-8 文本。请以 UTF-8 编码保存后重试。');
  }
  let length = 0;
  for (const _character of sql) if (++length > maxSqlCharacters) break;
  if (!sql.trim()) throw new Error('SQL 文件为空，请选择含 SQL 文本的文件。');
  const header = new Uint8Array(bytes, 0, Math.min(bytes.byteLength, 3));
  return { name: file.name, text: sql, bom: header[0] === 0xef && header[1] === 0xbb && header[2] === 0xbf,
    long: length > maxSqlCharacters };
}
