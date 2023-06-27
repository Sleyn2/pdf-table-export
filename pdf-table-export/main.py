import camelot
import tabula
import tkinter as tk
from tkinter import filedialog
import pywin.dialogs.list

root = tk.Tk()
root.withdraw()

file_path = filedialog.askopenfilename()
selected_library = pywin.dialogs.list.SelectFromList('Wybierz bibliotekę', ['tabulate', 'camelot'])

if selected_library == 0:
    tabula.convert_into(file_path, "tabulate-table.csv", pages='all')
    print('tabulate')
elif selected_library == 1:
    tables = camelot.read_pdf('data3.pdf', pages='1-end')
    tables.export('camelot-table.csv', f='csv')
    print('camelot')
