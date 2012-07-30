
"""
Contains the UserExpressionDialog class
"""

from PyQt4.QtGui import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QPalette
from PyQt4.QtCore import SIGNAL, Qt

class UserExpressionDialog(QDialog):
    """
    Allows user to enter a expression and have it applied.
    Sends a signal with the expresson on Apply
    """
    def __init__(self, parent):
        QDialog.__init__(self, parent)

        self.setWindowTitle("Enter Expression")

        self.exprEdit = QTextEdit(self)
        self.exprEdit.setAcceptRichText(False)

        self.hintEdit = QTextEdit(self)
        self.hintEdit.setText("Hint: Enter an expression using column names (ie 'col_a < 10'). " + 
"Combine more complicated expressions with '&' and '|'.\n" + 
"For example '(a < 10) & (b > 1)'\n" + 
"Any other numpy expressions also valid - columns are represented as numpy arrays")
        self.hintEdit.setReadOnly(True)
        # make background gray
        palette = self.hintEdit.palette()
        palette.setColor(QPalette.Base, Qt.lightGray);
        self.hintEdit.setPalette(palette)

        self.applyButton = QPushButton(self)
        self.applyButton.setText("Apply")

        self.closeButton = QPushButton(self)
        self.closeButton.setText("Close")

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.addWidget(self.applyButton)
        self.buttonLayout.addWidget(self.closeButton)

        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.addWidget(self.exprEdit)
        self.mainLayout.addWidget(self.hintEdit)
        self.mainLayout.addLayout(self.buttonLayout)

        self.connect(self.closeButton, SIGNAL("clicked()"), self.close)
        self.connect(self.applyButton, SIGNAL("clicked()"), self.applyExpression)


    def applyExpression(self):
        expression = self.exprEdit.toPlainText()
        self.emit(SIGNAL("newExpression(QString)"), expression)

