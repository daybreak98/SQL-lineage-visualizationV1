import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  analyzeSql,
  commitMetadata,
  convertSql,
  formatSql,
  getHealth,
  listMetadataColumns,
  listMetadataTables,
  previewMetadata,
} from '../client';

const mockFetch = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal('fetch', mockFetch);
});

describe('API Client', () => {
  // ── formatSql ──────────────────────────────────────────────

  describe('formatSql', () => {
    it('sends POST with sql and dialect', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'success',
            formatted_sql: 'SELECT 1',
            dialect: 'spark',
            diagnostics: [],
          }),
      });

      const result = await formatSql('select 1', 'spark');

      expect(result.formatted_sql).toBe('SELECT 1');
      expect(result.dialect).toBe('spark');
      expect(result.status).toBe('success');
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/sql/format',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sql: 'select 1', dialect: 'spark' }),
        }),
      );
    });

    it('defaults to spark dialect for unrecognized dialect', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'success',
            formatted_sql: 'SELECT 1',
            dialect: 'spark',
            diagnostics: [],
          }),
      });

      await formatSql('select 1', 'postgresql');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/sql/format',
        expect.objectContaining({
          body: JSON.stringify({ sql: 'select 1', dialect: 'spark' }),
        }),
      );
    });

    it('accepts hive dialect', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'success',
            formatted_sql: 'SELECT 1',
            dialect: 'hive',
            diagnostics: [],
          }),
      });

      await formatSql('select 1', '  Hive  ');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/sql/format',
        expect.objectContaining({
          body: JSON.stringify({ sql: 'select 1', dialect: 'hive' }),
        }),
      );
    });
  });

  describe('convertSql', () => {
    it('sends source and target dialects to convert endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'success',
            source_dialect: 'hive',
            target_dialect: 'spark',
            converted_sql: 'SELECT 1',
            elapsed_ms: 8,
            diagnostics: [],
          }),
      });

      const result = await convertSql('select 1', 'hive', 'spark');

      expect(result.converted_sql).toBe('SELECT 1');
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/sql/convert',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sql: 'select 1',
            source_dialect: 'hive',
            target_dialect: 'spark',
            pretty: true,
          }),
        }),
      );
    });

    it('maps sr alias to starrocks', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'success',
            source_dialect: 'starrocks',
            target_dialect: 'hive',
            converted_sql: 'SELECT 1',
            elapsed_ms: 5,
            diagnostics: [],
          }),
      });

      await convertSql('select 1', 'sr', 'hive');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/sql/convert',
        expect.objectContaining({
          body: JSON.stringify({
            sql: 'select 1',
            source_dialect: 'starrocks',
            target_dialect: 'hive',
            pretty: true,
          }),
        }),
      );
    });
  });

  // ── analyzeSql ─────────────────────────────────────────────

  describe('analyzeSql', () => {
    it('sends POST with full analysis options', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            analysis_id: 'test-id',
            status: 'success',
            tables_extracted: ['t1'],
            columns_extracted: ['c1'],
          }),
      });

      const result = await analyzeSql('SELECT * FROM t1', 'hive');

      expect(result.analysis_id).toBe('test-id');
      expect(result.status).toBe('success');
      expect(mockFetch).toHaveBeenCalledTimes(1);

      const callUrl = mockFetch.mock.calls[0][0];
      const callInit = mockFetch.mock.calls[0][1] as RequestInit;

      expect(callUrl).toBe('/api/sql/analyze');
      expect(callInit.method).toBe('POST');

      const body = JSON.parse(callInit.body as string);
      expect(body.sql).toBe('SELECT * FROM t1');
      expect(body.dialect).toBe('hive');
      expect(body.analysis_level).toBe('column');
      expect(body.analysis_options.include_graph).toBe(true);
      expect(body.analysis_options.include_diagnostics).toBe(true);
      expect(body.analysis_options.include_source_location).toBe(true);
      expect(body.analysis_options.include_expression_lineage).toBe(false);
    });

    it('handles partial analysis result', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            analysis_id: 'partial-id',
            status: 'partial',
            tables_extracted: ['t1'],
            columns_extracted: ['c1'],
            diagnostics_report: {
              diagnostics: [
                {
                  code: 'WARN_001',
                  level: 'warning',
                  message: 'Partial metadata',
                },
              ],
            },
          }),
      });

      const result = await analyzeSql('SELECT * FROM t1', 'spark');

      expect(result.status).toBe('partial');
      expect(result.diagnostics_report?.diagnostics).toHaveLength(1);
    });
  });

  // ── getHealth ──────────────────────────────────────────────

  describe('getHealth', () => {
    it('returns status ok', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'ok',
            service: 'sql-lineage',
            version: '1.0.0',
          }),
      });

      const result = await getHealth();

      expect(result.status).toBe('ok');
      expect(result.service).toBe('sql-lineage');
      expect(result.version).toBe('1.0.0');
      expect(mockFetch).toHaveBeenCalledWith('/api/health', undefined);
    });
  });

  // ── previewMetadata ────────────────────────────────────────

  describe('previewMetadata', () => {
    it('sends preview mode with metadata payload', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'preview_ready',
            import_batch_id: 'batch-1',
            metadata_version: 'v1',
            changes: [],
            diagnostics: [],
            summary: { total: 3 },
          }),
      });

      const payload = {
        schema_version: 'v1',
        metadata_version: 'v1',
        tables: [
          {
            name: 'users',
            columns: [{ name: 'id', data_type: 'INT' }],
          },
        ],
      };

      const result = await previewMetadata(payload);

      expect(result.status).toBe('preview_ready');
      expect(result.summary.total).toBe(3);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/metadata/import/preview',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ mode: 'preview', payload }),
        }),
      );
    });
  });

  // ── commitMetadata ─────────────────────────────────────────

  describe('commitMetadata', () => {
    it('sends commit mode', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            status: 'committed',
            import_batch_id: 'batch-1',
            metadata_version: 'v1',
            changes: [],
            diagnostics: [],
            summary: { total: 5 },
          }),
      });

      const payload = {
        schema_version: 'v1',
        metadata_version: 'v1',
        tables: [],
      };

      const result = await commitMetadata(payload);

      expect(result.status).toBe('committed');
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/metadata/import/commit',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ mode: 'commit', payload }),
        }),
      );
    });
  });

  // ── listMetadataTables ─────────────────────────────────────

  describe('listMetadataTables', () => {
    it('fetches table list from backend', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            tables: [{ name: 'users' }, { name: 'orders' }],
            total: 2,
          }),
      });

      const result = await listMetadataTables();

      expect(result.total).toBe(2);
      expect(mockFetch).toHaveBeenCalledWith('/api/metadata/tables', undefined);
    });
  });

  // ── listMetadataColumns ────────────────────────────────────

  describe('listMetadataColumns', () => {
    it('fetches all columns when no table filter', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            columns: [{ name: 'id' }, { name: 'name' }],
            total: 2,
          }),
      });

      const result = await listMetadataColumns();

      expect(result.total).toBe(2);
      expect(mockFetch).toHaveBeenCalledWith('/api/metadata/columns', undefined);
    });

    it('fetches columns filtered by table name', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({ columns: [], total: 0 }),
      });

      await listMetadataColumns('my_table');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/metadata/columns?table=my_table',
        undefined,
      );
    });

    it('URL-encodes table name with special characters', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({ columns: [], total: 0 }),
      });

      await listMetadataColumns('my table');

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/metadata/columns?table=my%20table',
        undefined,
      );
    });
  });

  // ── Error handling ─────────────────────────────────────────

  describe('error handling', () => {
    it('throws error with detail message on HTTP error', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Internal server error' }),
      });

      await expect(analyzeSql('SELECT 1', 'spark')).rejects.toThrow(
        'Internal server error',
      );
    });

    it('throws error with status code when no detail in response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve(null),
      });

      await expect(getHealth()).rejects.toThrow('HTTP 404');
    });

    it('throws error with status code when JSON parse fails', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: () => Promise.reject(new Error('Invalid JSON')),
      });

      await expect(getHealth()).rejects.toThrow('HTTP 502');
    });

    it('handles detail as object with message field', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () =>
          Promise.resolve({
            detail: { message: 'Validation failed' },
          }),
      });

      await expect(formatSql('', 'spark')).rejects.toThrow(
        'Validation failed',
      );
    });
  });
});
