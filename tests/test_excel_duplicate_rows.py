import ast, unittest
from pathlib import Path

class ParserDuplicateTests(unittest.TestCase):
    def test_parser_detects_duplicate_rows(self):
        root=Path(__file__).resolve().parents[1]
        source=root/'app/main/routes.py'
        tree=ast.parse(source.read_text())
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_parse_products_excel')
        # Exercise actual parser with an in-memory workbook and its existing helpers.
        from openpyxl import Workbook, load_workbook
        import io
        wb=Workbook(); sh=wb.active
        sh.append(['Material','Description','Price'])
        sh.append(['ABC','Primera',1.0]); sh.append(['abc','Segunda',2.0])
        buf=io.BytesIO(); wb.save(buf)
        def normalize_header(value): return value.strip().lower()
        def first_value(data, keys):
            return next((data[k] for k in keys if data.get(k) not in (None,'')),None)
        ns={'load_workbook':load_workbook,'io':io,'Dict':dict,'_normalize_header':normalize_header,
            '_first_value':first_value,'_normalize_reference_value':lambda x:str(x).strip() if x is not None else '',
            '_parse_bool':lambda x:None}
        helper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_catalog_price')
        exec(compile(ast.Module(body=[helper,node],type_ignores=[]),str(source),'exec'),ns)
        result,error=ns['_parse_products_excel'](buf.getvalue())
        self.assertIsNone(error)
        self.assertEqual(len(result['products']),1)
        self.assertEqual(result['skipped'],1)
        self.assertTrue(any('duplicada' in e for e in result['errors']))

if __name__=='__main__':unittest.main()
