import os
import tabula

file1 = os.getcwd() + "\\data1.pdf"
file2 = os.getcwd() + "\\data2.pdf"

table1 = tabula.read_pdf(file1, pages=1, multiple_tables=True)
table2 = tabula.read_pdf(file2, pages=2, multiple_tables=True)


print(table1, table2)

# output just the first page tables in the PDF to a CSV
tabula.convert_into(os.getcwd() + "\\data1.pdf", "Name_of_csv_file.csv")

# tabula.convert_into("pdf_file_name","Name_of_csv_file.csv",all = True)