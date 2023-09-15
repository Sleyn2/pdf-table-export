import pdf
import pandas as pd
import camelot
import tabula

index: int = 4
input_path = 'data/example-' + str(index) + '.pdf'
output_path_test = 'data/test/output' + str(index) + '.csv'
output_path_tabula = 'data/tabula/output' + str(index) + '.csv'
output_path_camelot = 'data/camelot/output' + str(index) + '.csv'

pdf = pdf.PDF.open(input_path)
table = pdf.pages[0].extract_table()
df = pd.DataFrame(table[1:], columns=table[0])
df.to_csv(output_path_test, index=False)

tabula.convert_into(input_path, output_path_tabula, pages='1')

tables = camelot.read_pdf(input_path, pages='1')
tables.export(output_path_camelot, f='csv')
