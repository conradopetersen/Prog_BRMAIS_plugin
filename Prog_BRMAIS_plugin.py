# -*- coding: utf-8 -*-
"""
Plugin QGIS para acesso a imagens da Planet Labs
"""
import os
import json
import tempfile
from datetime import datetime, timedelta
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtCore import QTimer
from PyQt5.QtCore import QVariant
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QSettings, QDate, QTimer, QEventLoop
from qgis.PyQt.QtWidgets import (QAction, QDialog, QMessageBox, 
                               QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QPushButton, QComboBox, QCheckBox,
                               QDateEdit, QProgressBar, QFileDialog,
                               QInputDialog, QWidget, QGroupBox, QGridLayout,
                               QSpinBox, QDoubleSpinBox, QSizePolicy, QRadioButton,
                               QToolButton)
from qgis.PyQt.QtGui import QIcon
from PyQt5.QtGui import QColor
from qgis.core import (QgsProject, QgsRasterLayer, QgsCoordinateReferenceSystem,
                      QgsCoordinateTransform, QgsRectangle, QgsContrastEnhancement, 
                      QgsMultiBandColorRenderer, QgsMapLayer, QgsVectorLayer,
                      QgsCategorizedSymbolRenderer, QgsRendererCategory, 
                      QgsFillSymbol, QgsSymbol, QgsSingleSymbolRenderer, QgsWkbTypes)
from qgis.utils import iface
import requests
try:
    # Tentativa para versões mais recentes da biblioteca
    import planet
    from planet import api
    from planet.api import filters
    HAS_PLANET_API = False
except (ImportError, AttributeError):
    # Fallback para versões mais antigas ou estrutura diferente
    try:
        import planet.api as api
        from planet.api import filters
        HAS_PLANET_API = True
    except (ImportError, AttributeError):
        # Se não conseguir importar de nenhuma forma
        HAS_PLANET_API = False

# Caminho do plugin
plugin_path = os.path.dirname(__file__)
FORM_CLASS, _ = uic.loadUiType(os.path.join(plugin_path, 'planet_plugin_dialog.ui'))
MIN_YEAR = 2016

class PlanetPlugin:
    """Plugin QGIS para acesso a imagens da Planet Labs"""
    
    def __init__(self, iface):
        self.iface = iface
        self.actions = []
        self.menu = 'Catalog Prog. Brasil Mais - SCCON/Planet'
        self.toolbar = self.iface.addToolBar('Brasil Mais')  #Nome da barra de ferramentas
        self.toolbar.setObjectName('BrasilMais') #Nome do objeto
        
        # Inicializar API client com None
        self.client = None
        
        # Configurações
        self.settings = QSettings()
        
        # Tentar carregar e validar a API Key automaticamente
        self.api_key = self.settings.value("planet_plugin/api_key", "")
        if self.api_key:
            self.validate_api_key_silently(self.api_key)
        
    def add_action(self, icon_path, text, callback, enabled_flag=True,
                  add_to_menu=True, add_to_toolbar=True, status_tip=None,
                  whats_this=None, parent=None):
        """Adicionar ação ao plugin"""
        
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        
        if status_tip is not None:
            action.setStatusTip(status_tip)
            
        if whats_this is not None:
            action.setWhatsThis(whats_this)
            
        if add_to_toolbar:
            self.toolbar.addAction(action)
            
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)
            
        self.actions.append(action)
        
        return action
        
    def initGui(self):
        """Inicializar a interface gráfica do plugin"""
        
        icon_path = os.path.join(plugin_path, 'icon.png')
        self.add_action(
            icon_path,
            text="Brasil MAIS Plugin",
            callback=self.run,
            parent=self.iface.mainWindow())
            
    def unload(self):
        """Remover o plugin da interface"""
        
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
            
        del self.toolbar
        
    def run(self):
        """Executar o plugin"""
        
        # Instanciar o diálogo
        dialog = PlanetPluginDialog(self)
        
        # Carregar API Key das configurações
        if self.api_key:
            dialog.apiKeyLineEdit.setText(self.api_key)
            dialog.is_api_key_valid = self.is_api_key_valid
            dialog.client = self.client
            
            # Habilitar as abas se a chave for válida
            if dialog.is_api_key_valid:
                dialog.tabWidget.setTabEnabled(1, True)
                dialog.tabWidget.setTabEnabled(2, True)
                dialog.tabWidget.setTabEnabled(3, True)
                
        # Mostrar o diálogo
        dialog.show()
        result = dialog.exec_()
        
        # Processar resultado
        if result:
            # Salvar API Key nas configurações apenas se o checkbox Register estiver marcado
            if dialog.is_api_key_valid and dialog.registerCheckBox.isChecked():
                self.api_key = dialog.apiKeyLineEdit.text()
                self.settings.setValue("planet_plugin/api_key", self.api_key)
            
            # Mesmo se não salvar, usar a chave para a sessão atual
            if dialog.is_api_key_valid:
                self.client = dialog.client
                self.is_api_key_valid = True
    
    def validate_api_key_silently(self, api_key):
        """Validar API Key sem mostrar diálogos"""
        try:
            response = requests.get(
                'https://api.planet.com/basemaps/v1/mosaics',
                auth=(api_key, '')
            )
            
            if response.status_code == 200:
                self.is_api_key_valid = True
                if HAS_PLANET_API:
                    self.client = api.ClientV1(api_key=api_key)
                else:
                    self.client = CustomPlanetClient(api_key)
                return True
            else:
                self.is_api_key_valid = False
                return False
                
        except Exception:
            self.is_api_key_valid = False
            return False
            

class PlanetPluginDialog(QDialog, FORM_CLASS):
    """Diálogo principal do plugin"""
    
    def __init__(self, plugin, parent=None):
        """Inicializar diálogo"""
        super(PlanetPluginDialog, self).__init__(parent)
        self.setupUi(self)
        self.plugin = plugin
        self.iface = plugin.iface
        
        # Atributos da API
        self.client = None
        self.is_api_key_valid = False
        
        # Configurar widgets
        self.setup_connections()
        self.setup_ui()

    def setup_ui(self):
        """Configurar interface inicial"""
        # Desativar abas até que a API seja validada
        self.tabWidget.setTabEnabled(1, False)  # Mosaicos mensais
        self.tabWidget.setTabEnabled(2, False)  # Imagens diárias
        self.tabWidget.setTabEnabled(3, False)  # Índices Espectrais (era NDVI)
        
        # Configurar datas
        # Definir ano mínimo como 2016
        min_year = 2016
        current_date = QDate.currentDate()
        current_year = current_date.year()
        years_diff = current_year - min_year
        months_diff = years_diff * 12
        
        # Configurar o estado inicial do checkbox Register
        self.registerCheckBox.setChecked(True)  # Marcado por padrão, ou False se preferir desmarcado

        # Configurar datas para intervalo de mosaicos mensais
        self.monthlyStartDateEdit.setDisplayFormat("MM/yyyy")
        self.monthlyStartDateEdit.setDate(current_date.addMonths(-1))
        self.monthlyStartDateEdit.setMaximumDate(current_date)
        self.monthlyStartDateEdit.setMinimumDate(QDate(min_year, 1, 1))
        
        # Data final (até o mês atual)
        self.monthlyEndDateEdit.setDisplayFormat("MM/yyyy")
        self.monthlyEndDateEdit.setDate(current_date)
        self.monthlyEndDateEdit.setMaximumDate(current_date)
        self.monthlyEndDateEdit.setMinimumDate(QDate(min_year, 1, 1)) 
        
        # Conectar o checkbox a uma função que habilita/desabilita a data final
        self.endDateCheckBox.stateChanged.connect(self.toggle_end_date)
        
        # Data para imagens diárias (até 30 dias atrás)
        self.dailyStartDateEdit.setDisplayFormat("dd/MM/yyyy")
        self.dailyStartDateEdit.setDate(current_date.addDays(-30))  
        self.dailyStartDateEdit.setMaximumDate(current_date)
        self.dailyStartDateEdit.setMinimumDate(QDate(min_year, 1, 1))  # Define 01/01/2016 como data mínima
                    
        self.dailyEndDateEdit.setDisplayFormat("dd/MM/yyyy")
        self.dailyEndDateEdit.setDate(current_date)
        self.dailyEndDateEdit.setMaximumDate(current_date)
        self.dailyEndDateEdit.setMinimumDate(QDate(min_year, 1, 1))  # Mesma data mínima
        
        # Configurar a aba de índices espectrais
        self.indexComboBox.addItems(["NDVI", "NDWI", "MSAVI2", "VARI", "MTVI2", "CIR"])
        
        # Configurar datas para índices espectrais
        self.indexStartDateEdit.setDisplayFormat("MM/yyyy")
        self.indexStartDateEdit.setDate(current_date.addMonths(-1))
        self.indexStartDateEdit.setMaximumDate(current_date)
        self.indexStartDateEdit.setMinimumDate(QDate(min_year, 1, 1))
        
        self.indexEndDateEdit.setDisplayFormat("MM/yyyy")
        self.indexEndDateEdit.setDate(current_date)
        self.indexEndDateEdit.setMaximumDate(current_date)
        self.indexEndDateEdit.setMinimumDate(QDate(min_year, 1, 1))
        
        # Configurar o checkbox para índices espectrais
        self.indexEndDateCheckBox.setChecked(True)
        
        # Adicionar opções de cobertura de nuvens
        self.dailyCloudComboBox.addItems(["< 10%", "< 20%", "< 50%", "Qualquer"])

        # Adicionar nova aba para Serviços SCCON - simplificada para alertas apenas
        self.scconTab = QWidget()
        self.tabWidget.addTab(self.scconTab, "Serviços SCCON")
        
        # Layout principal da aba SCCON
        sccon_layout = QVBoxLayout(self.scconTab)
        
        # Grupo de autenticação
        auth_group = QGroupBox("Autenticação SCCON")
        auth_layout = QGridLayout()
        
        # Criar o ícone de informação
        info_button = QToolButton()
        info_button.setIcon(QIcon(os.path.join(plugin_path, 'info_icon.png')))
        info_button.setAutoRaise(True)
        info_button.setToolTip(
            "Insira as credenciais de acesso (usuário e senha) e a URL do serviço de\n"
            "Alertas de detecção de mudanças. Essas informações são fornecidas pela\n"
            "Plataforma BRASIL MAIS na aba 'GEO SERVIÇOS E PLUGIN QGIS'"
        )

        # Adicionar o botão de informação no layout à direita do título
        auth_layout.addWidget(info_button, 0, 1, 1, 1, Qt.AlignRight | Qt.AlignTop)

        # Campos para URL, usuário e senha
        auth_layout.addWidget(QLabel("URL do serviço:"), 1, 0)
        self.scconUrlEdit = QLineEdit()
        self.scconUrlEdit.setPlaceholderText("https://geoservices-pf.sccon.com.br/service/alerts/wfs")
        auth_layout.addWidget(self.scconUrlEdit, 1, 1)

        auth_layout.addWidget(QLabel("Usuário:"), 2, 0)
        self.scconUserEdit = QLineEdit()
        auth_layout.addWidget(self.scconUserEdit, 2, 1)

        auth_layout.addWidget(QLabel("Senha:"), 3, 0)
        self.scconPassEdit = QLineEdit()
        self.scconPassEdit.setEchoMode(QLineEdit.Password)
        auth_layout.addWidget(self.scconPassEdit, 3, 1)

        # Checkbox e botão de conexão
        self.scconSaveAuth = QCheckBox("Salvar credenciais")
        auth_layout.addWidget(self.scconSaveAuth, 4, 0)
        self.connectScconBtn = QPushButton("Conectar")
        auth_layout.addWidget(self.connectScconBtn, 4, 1)
        self.connectScconBtn.clicked.connect(self.connect_to_sccon)

        auth_group.setLayout(auth_layout)
        sccon_layout.addWidget(auth_group)

        # Grupo de filtros - simplificado apenas para alertas
        self.filtersGroup = QGroupBox("Filtros de Alertas")
        self.filtersGroup.setEnabled(False)
        self.filters_layout = QGridLayout()

        # Filtros comuns (datas)
        self.filters_layout.addWidget(QLabel("Data início:"), 0, 0)
        self.startDateEdit = QDateEdit()
        self.startDateEdit.setDate(QDate.currentDate().addMonths(-3))
        self.startDateEdit.setCalendarPopup(True)
        self.filters_layout.addWidget(self.startDateEdit, 0, 1)

        self.filters_layout.addWidget(QLabel("Data fim:"), 1, 0)
        self.endDateEdit = QDateEdit()
        self.endDateEdit.setDate(QDate.currentDate())
        self.endDateEdit.setCalendarPopup(True)
        self.filters_layout.addWidget(self.endDateEdit, 1, 1)

        # Widget para filtros de alertas
        self.alertsFiltersWidget = QWidget()
        alerts_layout = QGridLayout(self.alertsFiltersWidget)
        alerts_layout.addWidget(QLabel("Área mínima (ha):"), 0, 0)
        self.areaMinSpin = QSpinBox()
        self.areaMinSpin.setRange(0, 10000)
        self.areaMinSpin.setValue(100)
        alerts_layout.addWidget(self.areaMinSpin, 0, 1)
        
        # Adicionar combobox para tipo de alerta
        alerts_layout.addWidget(QLabel("Tipo de alerta:"), 1, 0)
        self.alertTypeCombo = QComboBox()
        self.alertTypeCombo.addItems([
            "Todos", 
            "Cicatriz de Queimadas", 
            "Desmatamento - Corte Raso", 
            "Desmatamento - Degradacao",
            "Desmatamento - Degradacao - Corte Seletivo"
        ])
        alerts_layout.addWidget(self.alertTypeCombo, 1, 1)
        
        self.filters_layout.addWidget(self.alertsFiltersWidget, 2, 0, 1, 2)
        
        self.filtersGroup.setLayout(self.filters_layout)
        sccon_layout.addWidget(self.filtersGroup)

        # Botão para carregar dados
        self.loadScconDataBtn = QPushButton("Carregar Alertas")
        self.loadScconDataBtn.setEnabled(False)
        sccon_layout.addWidget(self.loadScconDataBtn)
        self.loadScconDataBtn.clicked.connect(self.load_sccon_data)
        
        # Configurações salvas
        if hasattr(self.plugin, 'sccon_url') and self.plugin.sccon_url:
            self.scconUrlEdit.setText(self.plugin.sccon_url)
        if hasattr(self.plugin, 'sccon_username') and self.plugin.sccon_username:
            self.scconUserEdit.setText(self.plugin.sccon_username)
        if hasattr(self.plugin, 'sccon_password') and self.plugin.sccon_password:
            self.scconPassEdit.setText(self.plugin.sccon_password)

    ## 2. Nova função para habilitar/desabilitar a data final com base no checkbox
    def toggle_end_date(self, state):
        """Habilitar ou desabilitar a data final com base no estado do checkbox"""
        self.monthlyEndDateEdit.setEnabled(state == Qt.Checked)
        self.monthlyEndLabel.setEnabled(state == Qt.Checked)
    
    def toggle_index_end_date(self, state):
        """Habilitar ou desabilitar a data final para índices com base no estado do checkbox"""
        self.indexEndDateEdit.setEnabled(state == Qt.Checked)
        self.indexEndLabel.setEnabled(state == Qt.Checked)
        
    def setup_connections(self):
        """Conectar sinais e slots"""
        # Planet API Keys
        self.validateButton.clicked.connect(self.validate_api_key)
        self.clearApiKeyButton.clicked.connect(self.clear_saved_api_key)
        
        # Planet Mosaics e Images
        self.loadMonthlyButton.clicked.connect(self.load_monthly_mosaic)
        self.loadDailyButton.clicked.connect(self.search_daily_images)
        self.loadNdviButton.clicked.connect(self.load_spectral_index_mosaic)
        self.currentExtentButton.clicked.connect(self.use_current_extent)
        
        # Checkboxes para datas
        self.endDateCheckBox.stateChanged.connect(self.toggle_end_date)
        self.indexEndDateCheckBox.stateChanged.connect(self.toggle_index_end_date)
        
        # Botões SCCON
        if hasattr(self, 'connectScconBtn'):
            self.connectScconBtn.clicked.connect(self.connect_to_sccon)
        if hasattr(self, 'loadScconDataBtn'):
            self.loadScconDataBtn.clicked.connect(self.load_sccon_data)
        
    def validate_api_key(self):
        api_key = self.apiKeyLineEdit.text().strip()
        
        if not api_key:
            QMessageBox.warning(self, "Erro", "Por favor, insira uma API Key")
            return
            
        try:
            # Usar autenticação básica em vez de parâmetro de consulta
            response = requests.get(
                'https://api.planet.com/basemaps/v1/mosaics',
                auth=(api_key, '')  # API Key como nome de usuário, senha vazia
            )
            
            if response.status_code == 200:
                registration_msg = ""
                if self.registerCheckBox.isChecked():
                    registration_msg = " e será salva para usos futuros"
                
                QMessageBox.information(
                    self, "Sucesso", 
                    f"API Key validada com sucesso{registration_msg}!"
                )
                
                self.is_api_key_valid = True
                self.client = api.ClientV1(api_key=api_key) if HAS_PLANET_API else None
                self.tabWidget.setTabEnabled(1, True)
                self.tabWidget.setTabEnabled(2, True)
                self.tabWidget.setTabEnabled(3, True)
            else:
                QMessageBox.warning(
                    self, "Erro", 
                    f"Falha na autenticação. Código de status: {response.status_code}. Mensagem: {response.text}"
                )
                self.is_api_key_valid = False
                
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao validar API Key: {str(e)}")
            self.is_api_key_valid = False

    def connect_to_sccon(self):
        """Testa a conexão com os serviços SCCON"""
        from qgis.core import QgsVectorLayer  # Importação explícita para evitar erro
        
        print("Tentando conectar ao SCCON...")
        url = self.scconUrlEdit.text().strip()
        username = self.scconUserEdit.text().strip()
        password = self.scconPassEdit.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Erro", "Por favor, informe a URL do serviço.")
            return
                
        self.progressBar.setValue(30)
        QApplication.processEvents()
        
        try:
            # Verificar se a URL termina com '/'
            if not url.endswith('/'):
                url += '/'
                
            # Detectar o tipo de serviço a partir da URL
            service_type = self.detect_service_type(url)
            
            # Adicionar parâmetros WFS apropriados se necessário
            if 'alerts/wfs' not in url and 'wfs' not in url:
                if 'alerts' in url.lower():
                    url += 'wfs'
                elif 'basemaps' in url.lower():
                    url += 'wfs'
                elif 'buildings' in url.lower():
                    url += 'wfs'
                elif 'roads' in url.lower():
                    url += 'wfs'
                    
            # Adicionar parâmetro userToken se URL não contiver
            if 'userToken=' not in url:
                url += '?userToken=' + username
                
            # Criar a string de conexão WFS exatamente como o QGIS faz
            typename = self.get_typename_for_service(service_type)
            datasource = f"pagingEnabled='true' restrictToRequestBBOX='1' srsname='EPSG:4326' typename='{typename}' url='{url}' username='{username}' password='{password}' version='1.1.0'"
            
            # Armazenar URL processada
            self.processed_url = url
            
            # Criar a camada de teste
            temp_layer = QgsVectorLayer(datasource, "Teste Conexão SCCON", "WFS")
            
            self.progressBar.setValue(70)
            QApplication.processEvents()
            
            if temp_layer.isValid():
                print("Camada WFS válida criada com sucesso")
                
                # Verificar se consegue acessar dados
                try:
                    # Tentar contar features (irá falhar se a conexão não estiver realmente funcionando)
                    count = 0
                    for _ in temp_layer.getFeatures():
                        count += 1
                        if count >= 3:  # Limite para não carregar demais
                            break
                    
                    print(f"Conseguiu acessar {count} features")
                    QMessageBox.information(self, "Sucesso", f"Conexão com o serviço SCCON ({service_type}) estabelecida com sucesso!")
                    
                    # Salvar credenciais se solicitado
                    if self.scconSaveAuth.isChecked():
                        self.plugin.settings.setValue("sccon_plugin/url", url)
                        self.plugin.settings.setValue("sccon_plugin/username", username)
                        self.plugin.settings.setValue("sccon_plugin/password", password)
                    else:
                        self.plugin.settings.remove("sccon_plugin/url")
                        self.plugin.settings.remove("sccon_plugin/username")
                        self.plugin.settings.remove("sccon_plugin/password")
                    
                    # Marcar conexão como bem-sucedida
                    self.is_connection_successful = True
                    
                    # Atualizar filtros com base no serviço detectado
                    self.update_sccon_filters(service_type)
                    
                    # Habilitar controles para filtros e carregamento
                    self.filtersGroup.setEnabled(True)
                    self.loadScconDataBtn.setEnabled(True)
                    
                except Exception as inner_e:
                    print(f"Camada válida, mas erro ao acessar dados: {str(inner_e)}")
                    QMessageBox.warning(self, "Aviso", f"Conexão estabelecida, mas erro ao verificar dados: {str(inner_e)}")
            else:
                error_msg = temp_layer.error().message() if hasattr(temp_layer, 'error') else "Erro desconhecido"
                print(f"Erro na criação da camada: {error_msg}")
                QMessageBox.warning(
                    self, "Erro", 
                    f"Não foi possível conectar ao serviço. Verifique suas credenciais e URL.\nErro: {error_msg}"
                )
                    
            self.progressBar.setValue(0)
                
        except Exception as e:
            self.progressBar.setValue(0)
            QMessageBox.critical(self, "Erro", f"Erro ao conectar: {str(e)}")
            import traceback
            print(traceback.format_exc())

    def detect_service_type(self, url):
        """Detecta o tipo de serviço a partir da URL - sempre retorna alertas"""
        return "Alertas de detecção de mudança"

    def get_typename_for_service(self, service_type):
        """Retorna o typename apropriado para o serviço - sempre alertas"""
        return "alerts"

    def update_sccon_filters(self, service_type=None):
        """Atualiza os filtros disponíveis - apenas para alertas"""
        # Como só temos alertas, não precisamos fazer nada além de garantir que esteja visível
        self.alertsFiltersWidget.setVisible(True)
        self.loadScconDataBtn.setText("Carregar Alertas")

    def load_sccon_data(self):
        """Carrega dados do serviço SCCON - apenas alertas"""
        url = self.scconUrlEdit.text().strip()
        username = self.scconUserEdit.text().strip()
        password = self.scconPassEdit.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Erro", "URL do serviço não encontrada. Por favor, conecte-se primeiro.")
            return
        
        try:
            # Definições sempre para alertas
            typename = "alerts"
            
            # Obter valores dos filtros
            date_start = self.startDateEdit.date().toString("yyyy-MM-dd")
            date_end = self.endDateEdit.date().toString("yyyy-MM-dd")
            area_min = self.areaMinSpin.value()
            alert_type = self.alertTypeCombo.currentText()
            
            # Construir SQL apenas com filtros básicos
            filters = f"area_ha > {area_min}"
            
            if date_start and date_end:
                filters += f" AND dat_depois BETWEEN '{date_start}' AND '{date_end}'"
                
            # Adicionar filtro de tipo se não for "Todos"
            if alert_type != "Todos":
                filters += f" AND tipo = '{alert_type}'"
                
            layer_name = f"Alertas SCCON"
            if date_start and date_end:
                layer_name += f" {date_start} a {date_end}"
            if area_min > 0:
                layer_name += f" (>{area_min}ha)"
            if alert_type != "Todos":
                layer_name += f" - {alert_type}"
            
            # Iniciar progresso
            self.progressBar.setValue(20)
            QApplication.processEvents()
            
            # Construir SQL
            sql = ""
            if filters:
                sql = f"SELECT * FROM {typename} WHERE {filters}"
            
            print(f"SQL Filter: {sql}")
            
            # Datasource
            datasource = (
                f"pagingEnabled='true' "
                f"srsname='EPSG:4326' "
                f"typename='{typename}' "
                f"url='{url}' "
                f"username='{username}' "
                f"password='{password}' "
            )
            
            # Adicionar filtro SQL se existir
            if sql:
                datasource += f"sql={sql}"
            
            self.progressBar.setValue(60)
            QApplication.processEvents()
            
            # Criar camada
            layer = QgsVectorLayer(datasource, layer_name, "WFS")
            
            self.progressBar.setValue(80)
            QApplication.processEvents()
            
            if layer.isValid():
                # Adicionar ao projeto
                QgsProject.instance().addMapLayer(layer)
                
                # Aplicar estilo para alertas
                self.apply_alert_style(layer, self.alertTypeCombo.currentText())
                
                self.progressBar.setValue(100)
                QMessageBox.information(
                    self, "Sucesso", 
                    f"Camada '{layer_name}' carregada com sucesso!\n"
                    f"Número de feições: {layer.featureCount()}"
                )
            else:
                error_msg = layer.error().message() if hasattr(layer, 'error') else "Erro desconhecido"
                self.progressBar.setValue(0)
                QMessageBox.warning(
                    self, "Erro", 
                    f"Não foi possível carregar os dados. Erro: {error_msg}"
                )
            
            # Resetar progresso após 2 segundos
            QTimer.singleShot(2000, lambda: self.progressBar.setValue(0))
            
        except Exception as e:
            self.progressBar.setValue(0)
            QMessageBox.critical(self, "Erro", f"Erro ao carregar dados: {str(e)}")
            import traceback
            print(traceback.format_exc())

    def apply_grid_style(self, layer):
        """Aplica estilo à camada de grade de imagens"""
        from qgis.core import QgsSymbol, QgsSingleSymbolRenderer
        
        # Criar um estilo simples para a grade
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(0, 0, 255, 50))  # Azul semitransparente
        symbol.symbolLayer(0).setStrokeColor(QColor(0, 0, 255))
        symbol.symbolLayer(0).setStrokeWidth(0.5)
        
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()


    def apply_buildings_style(self, layer):
        """Aplica estilo à camada de edificações"""
        from qgis.core import QgsSymbol, QgsSingleSymbolRenderer
        
        # Criar um estilo para edificações
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(255, 165, 0, 150))  # Laranja semitransparente
        symbol.symbolLayer(0).setStrokeColor(QColor(139, 69, 19))  # Marrom para contorno
        symbol.symbolLayer(0).setStrokeWidth(0.5)
        
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()


    def apply_roads_style(self, layer):
        """Aplica estilo à camada de estradas"""
        from qgis.core import QgsSymbol, QgsSingleSymbolRenderer
        
        # Criar um estilo para estradas
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        
        # Estilo depende do tipo de geometria (linha ou polígono)
        if layer.geometryType() == QgsWkbTypes.LineGeometry:
            symbol.setColor(QColor(255, 0, 0))  # Vermelho
            symbol.symbolLayer(0).setWidth(1.5)  # Linha mais larga
        else:  # Polígono
            symbol.setColor(QColor(255, 0, 0, 100))  # Vermelho semitransparente
            symbol.symbolLayer(0).setStrokeColor(QColor(255, 0, 0))
            symbol.symbolLayer(0).setStrokeWidth(0.8)
        
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def apply_alert_style(self, layer, alert_type):
        """Aplica estilo à camada de alertas com suporte a todos os tipos encontrados"""
        # Verificar campos disponíveis na camada
        fields = [field.name() for field in layer.fields()]
        
        # Tentar encontrar o campo tipo, caso insensível
        tipo_field_name = None
        for field in fields:
            if field.lower() == "tipo":
                tipo_field_name = field
                break
        
        # Se o tipo não for "Todos" ou o campo tipo não existir, usar estilo simples
        if alert_type != "Todos" or not tipo_field_name:
            # Cor padrão: vermelho semitransparente
            color = QColor(255, 0, 0, 128)
            
            if alert_type == "Cicatriz de Queimadas":
                color = QColor(255, 0, 0, 128)  # Vermelho
            elif alert_type == "Desmatamento - Corte Raso":
                color = QColor(255, 165, 0, 128)  # Laranja
            elif alert_type == "Desmatamento - Degradacao":
                color = QColor(255, 255, 0, 128)  # Amarelo
            elif alert_type == "Desmatamento - Degradacao - Corte Seletivo":
                color = QColor(0, 255, 0, 128)  # Verde
            
            symbol = QgsFillSymbol.createSimple({
                'color': f'{color.red()},{color.green()},{color.blue()},{color.alpha()}',
                'outline_color': f'{color.red()},{color.green()},{color.blue()},255',
                'outline_width': '0.5'
            })
            renderer = QgsSingleSymbolRenderer(symbol)
        else:
            # Estilo categorizado para "Todos"
            categorized = QgsCategorizedSymbolRenderer(tipo_field_name)
            
            # Definir cores para tipos conhecidos
            cores = {
                "Cicatriz de Queimadas": QColor(255, 0, 0, 128),  # Vermelho
                "Desmatamento - Corte Raso": QColor(255, 165, 0, 128),  # Laranja
                "Desmatamento - Degradacao": QColor(255, 255, 0, 128),  # Amarelo
                "Desmatamento - Degradacao - Corte Seletivo": QColor(0, 255, 0, 128),  # Verde
                "BLOW_DOWN": QColor(128, 0, 128, 128),  # Roxo
                "LANDSLIDES": QColor(165, 42, 42, 128),  # Marrom
                "SELECTIVE_EXTRACTION": QColor(0, 128, 128, 128),  # Ciano
                "DEGRADATION_PROCESS": QColor(0, 0, 255, 128),  # Azul
                "NULL": QColor(128, 128, 128, 128)  # Cinza para valores NULL
            }
            
            # Coletar valores únicos do campo tipo
            valores_unicos = set()
            for feature in layer.getFeatures():
                valor = feature[tipo_field_name]
                # Tratar valores NULL especialmente
                if valor is None or valor == "NULL" or valor == "":
                    valores_unicos.add("NULL")
                else:
                    valores_unicos.add(valor)
            
            # Adicionar categorias para cada valor único
            for valor in valores_unicos:
                # Se o valor está no nosso dicionário de cores predefinidas
                if valor in cores:
                    cor = cores[valor]
                else:
                    # Para valores não previstos, gerar cor aleatória
                    import random
                    r, g, b = random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)
                    cor = QColor(r, g, b, 128)
                
                # Criar símbolo para o valor
                symbol = QgsFillSymbol.createSimple({
                    'color': f'{cor.red()},{cor.green()},{cor.blue()},{cor.alpha()}',
                    'outline_color': f'{cor.red()},{cor.green()},{cor.blue()},255',
                    'outline_width': '0.5'
                })
                
                # Lidar com o caso especial de NULL
                if valor == "NULL":
                    # Para valores NULL, precisamos criar uma categoria especial
                    categoria = QgsRendererCategory(QVariant(), symbol, "NULL/Vazio")
                else:
                    categoria = QgsRendererCategory(valor, symbol, str(valor))
                
                categorized.addCategory(categoria)
            
            renderer = categorized
        
        # Aplicar renderer
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def load_monthly_mosaic(self):
        """Carrega mosaicos mensais para um período de datas selecionado"""
        try:
            if not self.is_api_key_valid:
                QMessageBox.warning(self, "Erro", "Valide sua API Key primeiro")
                return

            # Obter datas selecionadas
            start_date = self.monthlyStartDateEdit.date().toPyDate()
            
            # Configurar data final com base no checkbox
            if self.endDateCheckBox.isChecked():
                end_date = self.monthlyEndDateEdit.date().toPyDate()
            else:
                # Se não usar data final, definir como data atual
                end_date = QDate.currentDate().toPyDate()
            
            # Verificar se a data de início é anterior à data de fim
            if start_date > end_date:
                QMessageBox.warning(self, "Erro", "A data inicial deve ser anterior à data final")
                return
            
            # Calcular o número de meses no intervalo
            start_year, start_month = start_date.year, start_date.month
            end_year, end_month = end_date.year, end_date.month
            total_months = (end_year - start_year) * 12 + (end_month - start_month) + 1
            
            # Obter API Key
            api_key = self.apiKeyLineEdit.text().strip()
            
            # Inicializar contador para mosaicos carregados
            loaded_count = 0
            failed_count = 0
            
            # Calcular o número de meses no intervalo
            start_year, start_month = start_date.year, start_date.month
            end_year, end_month = end_date.year, end_date.month
            total_months = (end_year - start_year) * 12 + (end_month - start_month) + 1
            
            self.progressBar.setMaximum(total_months * 100)  # 100% para cada mês
            progress_step = 0

            # NOVO: Criar um grupo para os mosaicos
            root = QgsProject.instance().layerTreeRoot()
            group_name = f"Planet Monthly Mosaics ({start_date.strftime('%m/%Y')} - {end_date.strftime('%m/%Y')})"
            group = root.insertGroup(0, group_name)  # Inserir no topo da lista
            
            # Iterar pelos meses no intervalo
            current_year, current_month = start_year, start_month
            
            while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                # Atualizar a barra de progresso
                progress_base = progress_step * 100
                self.progressBar.setValue(progress_base + 10)
                QApplication.processEvents()
                
                # Montar o ID do mosaico para o mês atual
                mosaic_id = f"global_monthly_{current_year}_{current_month:02d}_mosaic"
                print(f"Procurando mosaico com ID: {mosaic_id}")
                
                # Montar a URL para XYZ Tiles
                xyz_url = (
                    f"type=xyz&url=https://tiles.planet.com/basemaps/v1/"
                    f"planet-tiles/{mosaic_id}/gmap/{{z}}/{{x}}/{{y}}.png"
                    f"?api_key={api_key}"
                    f"&zmin=0&zmax=18"
                )
                
                # Atualizar progresso
                self.progressBar.setValue(progress_base + 40)
                QApplication.processEvents()
                
                # Nome da camada (ex.: "December 2024")
                import calendar
                month_name = calendar.month_name[current_month]  # Nome do mês em inglês
                layer_name = f"{month_name} {current_year}"
                
                # Criar camada
                layer = QgsRasterLayer(xyz_url, layer_name, "wms")
                
                # Atualizar progresso
                self.progressBar.setValue(progress_base + 70)
                QApplication.processEvents()
                
                if layer.isValid():
                    # NOVO: Adicionar a camada ao grupo em vez de diretamente ao projeto
                    QgsProject.instance().addMapLayer(layer, False)  # False = não adicionar à legenda
                    group.addLayer(layer)  # Adicionar ao grupo
                    
                    loaded_count += 1
                    print(f"Mosaico carregado com sucesso: {layer_name}")
                else:
                    failed_count += 1
                    error_msg = layer.error().message() if hasattr(layer, 'error') else "Erro desconhecido"
                    print(f"Falha ao carregar mosaico {mosaic_id}: {error_msg}")
                
                # Atualizar progresso
                self.progressBar.setValue(progress_base + 100)
                QApplication.processEvents()
                
                # Avançar para o próximo mês
                progress_step += 1
                if current_month == 12:
                    current_month = 1
                    current_year += 1
                else:
                    current_month += 1
                    
                # Adicionar um intervalo entre o carregamento dos mosaicos
                if (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                    # Mostrar mensagem de espera
                    self.progressBar.setFormat(f"Carregando mosaicos... ({loaded_count + failed_count}/{total_months})")
                    QApplication.processEvents()
                    
                    # Criar um timer para aguardar antes de carregar o próximo mosaico
                    timer = QTimer()
                    timer.setSingleShot(True)
                    timer.start(600)  # Esperar 600 ms
                    
                    # Esperar o timer terminar - isso pausa a execução sem congelar a interface
                    loop = QEventLoop()
                    timer.timeout.connect(loop.quit)
                    loop.exec_()
                    
                    # Restaurar o formato original da barra de progresso
                    self.progressBar.setFormat("%p%")
            
            # Mostrar resultados
            if loaded_count > 0:
                QMessageBox.information(
                    self, "Sucesso",
                    f"Carregados {loaded_count} mosaicos com sucesso.\n"
                    f"{failed_count} mosaicos não puderam ser carregados."
                )
            else:
                QMessageBox.warning(
                    self, "Aviso",
                    f"Nenhum mosaico pôde ser carregado para o período selecionado.\n"
                    "Verifique se os mosaicos estão disponíveis na sua conta Planet Labs."
                )
            
            # Resetar a barra de progresso após 2 segundos
            self.progressBar.setValue(0)
            self.progressBar.setFormat("%p%")
            
        except Exception as e:
            self.progressBar.setValue(0)
            self.progressBar.setFormat("%p%")
            QMessageBox.critical(
                self, "Erro",
                f"Erro ao carregar mosaicos mensais: {str(e)}\n\n"
                "Verifique o console do QGIS (Plugins > Python Console) para mais detalhes."
            )
            import traceback
            print("*** ERRO AO CARREGAR MOSAICOS ***")
            print(traceback.format_exc())

    def create_wms_xml(self, mosaic_id, api_key):
        """Cria um arquivo XML de configuração GDAL_WMS para acessar os tiles da Planet"""
        xml = f"""<GDAL_WMS>
            <Service name="TMS">
                <ServerUrl>https://tiles.planet.com/basemaps/v1/planet-tiles/{mosaic_id}/gmap/${{z}}/${{x}}/${{inverted_y}}.png?api_key={api_key}</ServerUrl>
            </Service>
            <DataWindow>
                <UpperLeftX>-20037508.34</UpperLeftX>
                <UpperLeftY>20037508.34</UpperLeftY>
                <LowerRightX>20037508.34</LowerRightX>
                <LowerRightY>-20037508.34</LowerRightY>
                <TileLevel>18</TileLevel>
                <TileCountX>1</TileCountX>
                <TileCountY>1</TileCountY>
                <YOrigin>top</YOrigin>
            </DataWindow>
            <Projection>EPSG:3857</Projection>
            <BlockSizeX>256</BlockSizeX>
            <BlockSizeY>256</BlockSizeY>
            <BandsCount>3</BandsCount>
            <DataType>Byte</DataType>
            <ZeroBlockHttpCodes>400,404,403,500,503</ZeroBlockHttpCodes>
            <ZeroBlockOnServerException>true</ZeroBlockOnServerException>
            <Timeout>5</Timeout>
            <MaxConnections>10</MaxConnections>
            <Cache/>
        </GDAL_WMS>"""
        
        # Salvar em um arquivo temporário
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.xml', delete=False)
        temp_file.write(xml.encode('utf-8'))
        temp_file.close()
        
        return temp_file.name

    def configure_raster_rendering(self, layer):
        """Configurar a renderização do raster para melhor visualização"""
        if not layer.isValid():
            return
        
        # Configurar o renderizador para usar contraste automático
        provider = layer.dataProvider()
        renderer = QgsMultiBandColorRenderer(provider, 1, 2, 3)  # RGB
        
        # Aplicar contraste ampliado para cada banda
        for band_num in range(1, 4):
            ce = QgsContrastEnhancement(provider.dataType(band_num))
            ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
            if band_num == 1:
                renderer.setRedContrastEnhancement(ce)
            elif band_num == 2:
                renderer.setGreenContrastEnhancement(ce)
            elif band_num == 3:
                renderer.setBlueContrastEnhancement(ce)
        
        layer.setRenderer(renderer)
        layer.triggerRepaint()

    def register_auth_config(self, api_key):
        """Registra uma configuração de autenticação para uso com a Planet API"""
        from qgis.core import QgsAuthMethodConfig, QgsApplication
        
        # Criar configuração de autenticação básica
        auth_config = QgsAuthMethodConfig()
        auth_config.setName("PlanetAuth")
        auth_config.setMethod("Basic")
        auth_config.setConfig("username", api_key)
        auth_config.setConfig("password", "")  # A Planet API usa apenas a API key como "username"
        
        # Salvar a configuração no gerenciador de autenticação
        auth_manager = QgsApplication.authManager()
        success = False
        
        auth_id = auth_config.id()
        if auth_id:
            success = auth_manager.updateAuthenticationConfig(auth_config)
        else:
            success = auth_manager.storeAuthenticationConfig(auth_config)
            auth_id = auth_config.id()
            
        return auth_id if success else None

    def use_current_extent(self):
        """Usar a extensão atual do mapa para pesquisa"""
        # Obter a extensão atual do canvas
        canvas = self.iface.mapCanvas()
        extent = canvas.extent()
        
        # Transformar para WGS84 se necessário
        source_crs = canvas.mapSettings().destinationCrs()
        target_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        if source_crs != target_crs:
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
            extent = transform.transformBoundingBox(extent)
        
        # Formatar como texto
        bbox_text = f"{extent.xMinimum():.6f},{extent.yMinimum():.6f},{extent.xMaximum():.6f},{extent.yMaximum():.6f}"
        self.bboxLineEdit.setText(bbox_text)
    
    def search_daily_images(self):
        """Pesquisar imagens diárias na área de interesse e criar camadas vetoriais separadas por data"""
        if not self.is_api_key_valid:
            QMessageBox.warning(self, "Erro", "Por favor, valide sua API Key primeiro")
            return
            
        try:
            # Obter parâmetros da pesquisa
            bbox_text = self.bboxLineEdit.text().strip()
            if not bbox_text:
                QMessageBox.warning(self, "Erro", "Por favor, defina uma área de interesse")
                return
                
            # Converter bbox para coordenadas
            try:
                min_lon, min_lat, max_lon, max_lat = map(float, bbox_text.split(','))
            except:
                QMessageBox.warning(
                    self, "Erro", 
                    "Formato inválido para bbox. Use: min_lon,min_lat,max_lon,max_lat"
                )
                return
                
            # Obter datas
            start_date = self.dailyStartDateEdit.date().toPyDate()
            end_date = self.dailyEndDateEdit.date().toPyDate()
            
            # Verificar se as datas são válidas
            if start_date > end_date:
                QMessageBox.warning(self, "Erro", "A data inicial deve ser anterior à data final")
                return
                
            # Obter limite de nuvens
            cloud_text = self.dailyCloudComboBox.currentText()
            cloud_percent = 100  # Padrão: qualquer
            if "< 10%" in cloud_text:
                cloud_percent = 10
            elif "< 20%" in cloud_text:
                cloud_percent = 20
            elif "< 50%" in cloud_text:
                cloud_percent = 50
                    
            # Mostrar barra de progresso
            self.progressBar.setValue(10)
            QApplication.processEvents()
            
            # Obter API key
            api_key = self.apiKeyLineEdit.text().strip()
            
            # Construir filtros
            start_date_str = start_date.strftime("%Y-%m-%dT00:00:00Z")
            end_date_str = end_date.strftime("%Y-%m-%dT23:59:59Z")
            
            # Construir geometria GeoJSON para o filtro
            geometry = {
                "type": "Polygon",
                "coordinates": [[
                    [min_lon, min_lat],
                    [max_lon, min_lat],
                    [max_lon, max_lat],
                    [min_lon, max_lat],
                    [min_lon, min_lat]
                ]]
            }
            
            # Construir filtros como objetos JSON
            filter_json = {
                "type": "AndFilter",
                "config": [
                    {
                        "type": "GeometryFilter",
                        "field_name": "geometry",
                        "config": geometry
                    },
                    {
                        "type": "DateRangeFilter",
                        "field_name": "acquired",
                        "config": {
                            "gte": start_date_str,
                            "lte": end_date_str
                        }
                    },
                    {
                        "type": "RangeFilter",
                        "field_name": "cloud_cover",
                        "config": {
                            "lt": cloud_percent / 100.0
                        }
                    }
                ]
            }
            
            # Payload para a requisição
            payload = {
                "item_types": ["PSScene"],
                "filter": filter_json
            }
            
            # Atualizar barra de progresso
            self.progressBar.setValue(30)
            QApplication.processEvents()
            
            # Fazer a requisição HTTP
            try:
                headers = {"Content-Type": "application/json"}
                response = requests.post(
                    "https://api.planet.com/data/v1/quick-search",
                    auth=(api_key, ''),
                    headers=headers,
                    json=payload
                )
                
                self.progressBar.setValue(50)
                QApplication.processEvents()
                
                if response.status_code == 200:
                    results = response.json()
                    features = results.get('features', [])
                    
                    # Verificar se temos resultados
                    if not features:
                        QMessageBox.information(
                            self, "Informação", 
                            "Nenhuma imagem encontrada com os critérios especificados"
                        )
                        self.progressBar.setValue(0)
                        return
                    
                    # Organizar features por data
                    from collections import defaultdict
                    features_by_date = defaultdict(list)
                    
                    for feature in features:
                        properties = feature.get('properties', {})
                        acquired = properties.get('acquired', '')
                        
                        # Extrair apenas a data (sem a hora)
                        if 'T' in acquired:
                            date_only = acquired.split('T')[0]
                        else:
                            date_only = acquired
                            
                        # Adicionar a feature ao dicionário agrupado por data
                        features_by_date[date_only].append(feature)
                    
                    # Criar uma camada vetorial para cada data
                    from qgis.core import (QgsVectorLayer, QgsFeature, QgsGeometry, 
                                    QgsField, QgsFields, QgsProject, QgsWkbTypes,
                                    QgsPointXY, QgsMapLayer)
                    from PyQt5.QtCore import QVariant
                    
                    # Definir campos comuns para todas as camadas
                    fields = QgsFields()
                    fields.append(QgsField("id", QVariant.String))
                    fields.append(QgsField("hora", QVariant.String))
                    fields.append(QgsField("nuvens", QVariant.Double))
                    fields.append(QgsField("item_id", QVariant.String))
                    
                    # Lista para armazenar os IDs das camadas criadas
                    layer_ids = []
                    
                    # Criar um grupo para organizar as camadas
                    root = QgsProject.instance().layerTreeRoot()
                    search_dates = f"{start_date.strftime('%d-%m-%Y')}_{end_date.strftime('%d-%m-%Y')}"
                    cloud_info = f"nuvens-{cloud_percent}pct"
                    group_name = f"Planet_Imagens_{search_dates}_{cloud_info}"
                    group = root.insertGroup(0, group_name)
                    
                    # Contador de progresso
                    total_dates = len(features_by_date)
                    date_count = 0
                    
                    # Para cada data, criar uma camada separada
                    for date_str, date_features in sorted(features_by_date.items()):
                        date_count += 1
                        progress = 50 + int(40 * (date_count / total_dates))
                        self.progressBar.setValue(progress)
                        self.progressBar.setFormat(f"Processando data {date_count}/{total_dates}...")
                        QApplication.processEvents()
                        
                        # Formatar a data para exibição amigável (YYYY-MM-DD para DD/MM/YYYY)
                        try:
                            display_date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d/%m/%Y')
                        except:
                            display_date = date_str
                        
                        # Nome da camada para esta data
                        layer_name = f"Planet_Imagens_{display_date}"
                        
                        # Criar camada temporária em memória
                        layer = QgsVectorLayer("Polygon?crs=EPSG:4326", layer_name, "memory")
                        provider = layer.dataProvider()
                        provider.addAttributes(fields.toList())
                        layer.updateFields()
                        
                        # Adicionar features à camada
                        feature_count = 0
                        for feature in date_features:
                            feature_count += 1
                            item_id = feature.get('id', '')
                            properties = feature.get('properties', {})
                            acquired = properties.get('acquired', '')
                            cloud = properties.get('cloud_cover', 0) * 100.0
                            
                            # Extrair hora da aquisição
                            time_str = ""
                            if 'T' in acquired and len(acquired.split('T')) > 1:
                                time_part = acquired.split('T')[1]
                                if 'Z' in time_part:
                                    time_str = time_part.split('Z')[0][:5]  # Formato HH:MM
                                else:
                                    time_str = time_part[:5]
                            
                            # Extrair geometria da imagem
                            geom = feature.get('geometry', {})
                            
                            try:
                                # Criar feature
                                qgs_feat = QgsFeature()
                                
                                # Converter GeoJSON para QgsGeometry
                                coords = geom.get('coordinates', [])
                                if geom.get('type') == 'Polygon' and coords:
                                    qgs_geom = QgsGeometry.fromPolygonXY([[QgsPointXY(pt[0], pt[1]) for pt in coords[0]]])
                                else:
                                    # Fallback para bbox
                                    bbox = properties.get('bbox', [0, 0, 0, 0])
                                    if len(bbox) == 4:
                                        x_min, y_min, x_max, y_max = bbox
                                        qgs_geom = QgsGeometry.fromPolygonXY([[
                                            QgsPointXY(x_min, y_min),
                                            QgsPointXY(x_max, y_min),
                                            QgsPointXY(x_max, y_max),
                                            QgsPointXY(x_min, y_max),
                                            QgsPointXY(x_min, y_min)
                                        ]])
                                    else:
                                        # Se não houver geometria ou bbox válidas, pular esta feature
                                        print(f"Sem geometria válida para a imagem {item_id}")
                                        continue
                                
                                qgs_feat.setGeometry(qgs_geom)
                                
                                # Definir atributos
                                qgs_feat.setAttributes([
                                    f"Imagem-{feature_count}",
                                    time_str,
                                    cloud,
                                    item_id
                                ])
                                
                                # Adicionar feature à camada
                                provider.addFeature(qgs_feat)
                            except Exception as e:
                                print(f"Erro ao adicionar feature: {str(e)}")
                                continue
                        
                        # Atualizar a camada
                        layer.updateExtents()
                        
                        # Configurar estilo da camada para melhor visualização
                        from qgis.core import QgsFillSymbol
                        symbol = QgsFillSymbol.createSimple({
                            'color': '255,0,0,30',  # Vermelho semitransparente
                            'outline_color': '255,0,0,255',
                            'outline_width': '0.5'
                        })
                        layer.renderer().setSymbol(symbol)
                        
                        # Adicionar camada ao projeto dentro do grupo
                        QgsProject.instance().addMapLayer(layer, False)
                        group.addLayer(layer)
                        
                        # Guardar o ID da camada
                        layer_ids.append(layer.id())
                    
                    # Armazenar todos os IDs das camadas criadas para uso posterior
                    self.daily_images_layer_ids = layer_ids
                    
                    # Atualizar barra de progresso
                    self.progressBar.setValue(100)
                    self.progressBar.setFormat("%p%")
                    QApplication.processEvents()
                    
                    # Adicionar botão para carregar imagens selecionadas
                    if hasattr(self, 'loadSelectedButton'):
                        # Se o botão já existe, apenas garantir que está visível e habilitado
                        self.loadSelectedButton.setVisible(True)
                        self.loadSelectedButton.setEnabled(True)
                    else:
                        # Criar o botão se não existir
                        self.loadSelectedButton = QPushButton("Carregar Imagens Selecionadas")
                        self.loadSelectedButton.clicked.connect(self.load_selected_daily_images)
                        
                        # Adicionar ao layout da aba de imagens diárias
                        try:
                            # Adicionar abaixo do botão de pesquisa
                            if hasattr(self, 'loadDailyButton') and self.loadDailyButton.parent():
                                parent_layout = self.loadDailyButton.parent().layout()
                                if parent_layout:
                                    index = parent_layout.indexOf(self.loadDailyButton)
                                    parent_layout.insertWidget(index + 1, self.loadSelectedButton)
                                else:
                                    # Caso não consiga identificar o layout, criar um layout para o botão
                                    container = QWidget()
                                    layout = QVBoxLayout(container)
                                    layout.addWidget(self.loadSelectedButton)
                                    # Adicionar o container em algum lugar da interface
                                    self.tabWidget.findChild(QWidget, "dailyTab").layout().addWidget(container)
                            else:
                                # Último recurso: adicionar ao layout da aba
                                self.tabWidget.findChild(QWidget, "dailyTab").layout().addWidget(self.loadSelectedButton)
                        except Exception as e:
                            print(f"Erro ao adicionar botão: {str(e)}")
                            try:
                                # Tente adicionar o botão ao layout principal como último recurso
                                if hasattr(self, 'layout'):
                                    self.layout().addWidget(self.loadSelectedButton)
                            except:
                                pass  # Último recurso falhou
                    
                    # Exibir mensagem de sucesso com instruções
                    QMessageBox.information(
                        self, "Sucesso", 
                        f"Foram encontradas imagens em {total_dates} dias diferentes.\n\n"
                        f"Cada dia foi carregado como uma camada separada no grupo '{group_name}'.\n\n"
                        "Para carregar imagens:\n"
                        "1. Selecione uma ou mais camadas no painel de camadas\n"
                        "2. Selecione os polígonos desejados, utilizando a ferramenta de seleção de feições\n"
                        "3. Clique no botão 'Carregar Imagens Selecionadas'"
                    )
                else:
                    # Imprimir detalhes do erro para debug
                    print(f"Erro na API: {response.status_code}")
                    print(f"Conteúdo da resposta: {response.text}")
                    
                    QMessageBox.warning(
                        self, "Erro", 
                        f"Erro na busca: {response.status_code} - {response.text}"
                    )
            except Exception as e:
                QMessageBox.critical(
                    self, "Erro", 
                    f"Erro ao fazer a requisição: {str(e)}"
                )
                import traceback
                print(traceback.format_exc())
            
            # Resetar progresso
            QTimer.singleShot(2000, lambda: self.progressBar.setValue(0))
            
        except Exception as e:
            self.progressBar.setValue(0)
            QMessageBox.critical(self, "Erro", f"Erro ao pesquisar imagens diárias: {str(e)}")
            QTimer.singleShot(2000, lambda: self.progressBar.setValue(0))

        except Exception as e:
            self.progressBar.setValue(0)
            self.progressBar.setFormat("%p%")
            QMessageBox.critical(self, "Erro", f"Erro ao pesquisar imagens diárias: {str(e)}")
            import traceback
            print("*** ERRO AO PESQUISAR IMAGENS DIÁRIAS ***")
            print(traceback.format_exc())

    def load_selected_daily_images(self):
        """Carrega as imagens diárias selecionadas nas diferentes camadas de polígonos"""
        try:
            # Verificar camadas disponíveis
            selected_features = []
            layers_with_selection = []
            
            # Verificar a camada ativa primeiro
            active_layer = iface.activeLayer()
            if active_layer and active_layer.name().startswith("Planet_Imagens_") and active_layer.type() == QgsMapLayer.VectorLayer:
                if active_layer.selectedFeatureCount() > 0:
                    print(f"Camada ativa encontrada com seleção: {active_layer.name()}")
                    print(f"Número de feições selecionadas: {active_layer.selectedFeatureCount()}")
                    
                    # Armazenar a camada e suas features selecionadas como par
                    features = active_layer.selectedFeatures()
                    selected_features.extend(features)
                    
                    # Armazenar a associação entre features e camada
                    layers_with_selection.append(active_layer)
            
            # Se não encontrou na camada ativa, procurar em outras camadas
            if not selected_features:
                for lyr in QgsProject.instance().mapLayers().values():
                    if lyr != active_layer and lyr.name().startswith("Planet_Imagens_") and lyr.type() == QgsMapLayer.VectorLayer:
                        if lyr.selectedFeatureCount() > 0:
                            print(f"Camada adicional com seleção: {lyr.name()}")
                            print(f"Número de feições selecionadas: {lyr.selectedFeatureCount()}")
                            features = lyr.selectedFeatures()
                            selected_features.extend(features)
                            layers_with_selection.append(lyr)
            
            # Se ainda não encontrou features selecionadas
            if not selected_features:
                QMessageBox.warning(
                    self, "Seleção vazia", 
                    "Selecione pelo menos uma imagem em uma das camadas antes de carregar."
                )
                return
            
            # Iniciar barra de progresso
            self.progressBar.setValue(10)
            QApplication.processEvents()
            
            # Obter API Key
            api_key = self.apiKeyLineEdit.text().strip()
            
            # Contador de imagens carregadas com sucesso
            success_count = 0
            total_count = len(selected_features)
            
            print(f"Total de features selecionadas: {total_count}")
            
            # Processar cada feature selecionada
            for i, feature in enumerate(selected_features):
                try:
                    # Extrair ID da imagem do campo item_id
                    if 'item_id' not in [field.name() for field in feature.fields()]:
                        print(f"Feature {i+1}: Campo 'item_id' não encontrado")
                        continue
                    
                    full_item_id = feature.attribute('item_id')
                    if not full_item_id:
                        print(f"Feature {i+1}: Campo 'item_id' está vazio")
                        continue
                    
                    print(f"Feature {i+1}: ID completo: {full_item_id}")
                    
                    # Usar o ID completo em vez de processá-lo
                    item_id = full_item_id  # Usar o ID completo
                    print(f"Usando ID completo: {item_id}")
                    
                    # Obter data a partir da camada a que esta feature pertence
                    date_str = ""
                    # Use a camada salva na lista layers_with_selection
                    for layer in layers_with_selection:
                        # Obter o nome da camada que tem a formatação Planet_Imagens_DD/MM/YYYY
                        layer_name = layer.name()
                        if layer_name.startswith("Planet_Imagens_"):
                            # Extrair a data do nome da camada
                            parts = layer_name.split("_")
                            if len(parts) > 2:
                                date_str = parts[2]
                                break
                    
                    # Informações adicionais para o nome da camada
                    hora_str = ""
                    if 'hora' in [field.name() for field in feature.fields()]:
                        hora_str = feature.attribute('hora')
                    
                    # Atualizar progresso
                    progress = 10 + int(90 * ((i+1) / total_count))
                    self.progressBar.setValue(progress)
                    self.progressBar.setFormat(f"Carregando imagem {i+1} de {total_count}...")
                    QApplication.processEvents()
                    
                    # URL que comprovadamente funciona
                    url = f"type=xyz&url=https://tiles.planet.com/data/v1/PSScene/{item_id}/{{z}}/{{x}}/{{y}}.png?api_key={api_key}"
                    print(f"Tentando URL: {url.split('?')[0]}")
                    
                    # Nome da camada
                    layer_name = f"{date_str} {hora_str} (ID: {item_id})"
                    
                    # Criar camada
                    raster_layer = QgsRasterLayer(url, layer_name, "wms")
                    
                    if raster_layer.isValid():
                        QgsProject.instance().addMapLayer(raster_layer)
                        success_count += 1
                        success = True
                        print(f"Sucesso com a URL: {layer_name}")
                    else:
                        error_msg = raster_layer.error().message() if hasattr(raster_layer, 'error') else "Erro desconhecido"
                        print(f"Falha com a URL: {error_msg}")
                        
                        # Tentar com abordagem XML para casos de timeout
                        print("Tentando abordagem XML com timeout aumentado...")
                        xml_file = self.create_wms_xml_for_item(item_id, api_key)
                        raster_layer_xml = QgsRasterLayer(xml_file, layer_name + " (XML)", "gdal")
                        
                        if raster_layer_xml.isValid():
                            QgsProject.instance().addMapLayer(raster_layer_xml)
                            success_count += 1
                            success = True
                            print(f"Sucesso com abordagem XML: {layer_name}")
                        else:
                            xml_error = raster_layer_xml.error().message() if hasattr(raster_layer_xml, 'error') else "Erro desconhecido"
                            print(f"Falha com abordagem XML: {xml_error}")
                            print(f"Todas as tentativas falharam para a imagem {item_id}")
                    
                except Exception as e:
                    print(f"Erro ao processar imagem {i+1}/{total_count}: {str(e)}")
                    import traceback
                    print(traceback.format_exc())
            
            # Finalizar progresso
            self.progressBar.setValue(100)
            self.progressBar.setFormat("%p%")
            QApplication.processEvents()
            
            # Mostrar mensagem de resultado
            if success_count > 0:
                QMessageBox.information(
                    self, "Sucesso", 
                    f"Foram carregadas {success_count} de {total_count} imagens selecionadas."
                )
            else:
                QMessageBox.warning(
                    self, "Erro", 
                    "Não foi possível carregar nenhuma das imagens selecionadas.\n\n"
                    "Verificar no Console do Python (Plugins > Console do Python) os detalhes do erro.\n\n"
                    "Obs: Pode ser necessário ajustar o formato do ID ou URL da API Planet."
                )
            
            # Resetar progresso após 2 segundos
            QTimer.singleShot(2000, lambda: self.progressBar.setValue(0))
            
        except Exception as e:
            self.progressBar.setValue(0)
            self.progressBar.setFormat("%p%")
            QMessageBox.critical(self, "Erro", f"Erro ao carregar imagens: {str(e)}")
            import traceback
            print("*** ERRO AO CARREGAR IMAGENS SELECIONADAS ***")
            print(traceback.format_exc())



    # Adicionar esta função na classe
    def create_wms_xml_for_item(self, item_id, api_key):
        """Criar configuração XML para acessar uma imagem específica com timeout aumentado"""
        xml = f"""<GDAL_WMS>
            <Service name="TMS">
                <ServerUrl>https://tiles.planet.com/data/v1/PSScene/{item_id}/${{z}}/${{x}}/${{inverted_y}}.png?api_key={api_key}</ServerUrl>
            </Service>
            <DataWindow>
                <UpperLeftX>-20037508.34</UpperLeftX>
                <UpperLeftY>20037508.34</UpperLeftY>
                <LowerRightX>20037508.34</LowerRightX>
                <LowerRightY>-20037508.34</LowerRightY>
                <TileLevel>18</TileLevel>
                <TileCountX>1</TileCountX>
                <TileCountY>1</TileCountY>
                <YOrigin>top</YOrigin>
            </DataWindow>
            <Projection>EPSG:3857</Projection>
            <BlockSizeX>256</BlockSizeX>
            <BlockSizeY>256</BlockSizeY>
            <BandsCount>3</BandsCount>
            <DataType>Byte</DataType>
            <ZeroBlockHttpCodes>400,404,403,500,503</ZeroBlockHttpCodes>
            <ZeroBlockOnServerException>true</ZeroBlockOnServerException>
            <Timeout>120</Timeout>
            <MaxConnections>10</MaxConnections>
            <Cache/>
        </GDAL_WMS>"""
        
        # Salvar em arquivo temporário
        import tempfile
        temp_file = tempfile.NamedTemporaryFile(suffix='.xml', delete=False)
        temp_file.write(xml.encode('utf-8'))
        temp_file.close()
        
        return temp_file.name

    def load_spectral_index_mosaic(self):
        """Carrega mosaicos com o índice espectral selecionado para um período"""
        if not self.is_api_key_valid:
            QMessageBox.warning(self, "Erro", "Por favor, valide sua API Key primeiro")
            return
            
        try:
            # Obter datas selecionadas
            start_date = self.indexStartDateEdit.date().toPyDate()
            
            # Configurar data final com base no checkbox
            if self.indexEndDateCheckBox.isChecked():
                end_date = self.indexEndDateEdit.date().toPyDate()
            else:
                # Se não usar data final, carregar apenas o mês inicial
                end_date = start_date
            
            # Verificar se a data de início é anterior à data de fim
            if start_date > end_date:
                QMessageBox.warning(self, "Erro", "A data inicial deve ser anterior à data final")
                return
            
            # Obter o índice selecionado
            selected_index = self.indexComboBox.currentText()
            proc_param = self.get_proc_param_for_index(selected_index)
            
            # Mostrar barra de progresso
            self.progressBar.setValue(10)
            QApplication.processEvents()
            
            # API Key
            api_key = self.apiKeyLineEdit.text().strip()
            
            # Calcular o número de meses no intervalo
            start_year, start_month = start_date.year, start_date.month
            end_year, end_month = end_date.year, end_date.month
            total_months = (end_year - start_year) * 12 + (end_month - start_month) + 1
            
            self.progressBar.setMaximum(total_months * 100)  # 100% para cada mês
            progress_step = 0
            
            # NOVO: Criar um grupo para os mosaicos de índices
            root = QgsProject.instance().layerTreeRoot()
            group_name = f"Planet {selected_index} ({start_date.strftime('%m/%Y')} - {end_date.strftime('%m/%Y')})"
            group = root.insertGroup(0, group_name)  # Inserir no topo da lista
            
            # Inicializar contadores de sucesso/falha
            loaded_count = 0
            failed_count = 0
            
            # Iterar pelos meses no intervalo
            current_year, current_month = start_year, start_month
            
            while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                # Atualizar a barra de progresso
                progress_base = progress_step * 100
                self.progressBar.setValue(progress_base + 10)
                self.progressBar.setFormat(f"Carregando {selected_index} {current_month:02d}/{current_year}...")
                QApplication.processEvents()
                
                # Formatar data para o mosaico
                date_str = f"{current_year}-{current_month:02d}"
                
                # Formato específico para os mosaicos
                mosaic_name = f"planet_medres_normalized_analytic_{date_str}_mosaic"
                
                # Log para debug
                print(f"Tentando carregar mosaico {selected_index}: {mosaic_name}")
                
                # Atualizar barra de progresso
                self.progressBar.setValue(progress_base + 40)
                QApplication.processEvents()
                
                # Montar a URL para visualização XYZ com processamento do índice selecionado
                layer_uri = (
                    f"type=xyz&"
                    f"url=https://tiles.planet.com/basemaps/v1/planet-tiles/{mosaic_name}/gmap/{{z}}/{{x}}/{{y}}.png?proc={proc_param}&"
                    f"username={api_key}&"
                    f"password=&"
                    f"zmin=0&"
                    f"zmax=18"
                )
                
                # Adicionar camada ao QGIS
                layer_name = f"Planet {selected_index} {date_str}"
                layer = QgsRasterLayer(layer_uri, layer_name, "wms")
                
                try_alternative = False
                
                if layer.isValid():
                    # Adicionar ao grupo do projeto
                    QgsProject.instance().addMapLayer(layer, False)  # False = não adicionar à legenda
                    group.addLayer(layer)  # Adicionar ao grupo
                    
                    # Aplicar renderização específica para o índice
                    self._configure_index_rendering(layer, selected_index)
                    
                    loaded_count += 1
                    print(f"Mosaico {selected_index} carregado com sucesso: {layer_name}")
                else:
                    try_alternative = True
                    
                # Se a primeira tentativa falhou, tentar formato alternativo
                if try_alternative:
                    # Tentar formato alternativo com underscores em vez de hífens
                    alt_mosaic_name = f"planet_medres_normalized_analytic_{current_year}_{current_month:02d}_mosaic"
                    
                    alt_layer_uri = (
                        f"type=xyz&"
                        f"url=https://tiles.planet.com/basemaps/v1/planet-tiles/{alt_mosaic_name}/gmap/{{z}}/{{x}}/{{y}}.png?proc={proc_param}&"
                        f"username={api_key}&"
                        f"password=&"
                        f"zmin=0&"
                        f"zmax=18"
                    )
                    
                    alt_layer = QgsRasterLayer(alt_layer_uri, layer_name, "wms")
                    
                    if alt_layer.isValid():
                        QgsProject.instance().addMapLayer(alt_layer, False)
                        group.addLayer(alt_layer)
                        
                        # Aplicar renderização específica para o índice
                        self._configure_index_rendering(alt_layer, selected_index)
                        
                        loaded_count += 1
                        print(f"Mosaico {selected_index} carregado com formato alternativo: {layer_name}")
                    else:
                        failed_count += 1
                        print(f"Falha ao carregar mosaico {selected_index} para {date_str}")
                
                # Atualizar progresso
                self.progressBar.setValue(progress_base + 100)
                QApplication.processEvents()
                
                # Avançar para o próximo mês
                progress_step += 1
                if current_month == 12:
                    current_month = 1
                    current_year += 1
                else:
                    current_month += 1
                    
                # Adicionar um pequeno intervalo entre o carregamento dos mosaicos
                if (current_year < end_year) or (current_year == end_year and current_month <= end_month):
                    # Criar um timer para aguardar antes de carregar o próximo mosaico
                    timer = QTimer()
                    timer.setSingleShot(True)
                    timer.start(600)  # Esperar 600 ms
                    
                    # Esperar o timer terminar - isso pausa a execução sem congelar a interface
                    loop = QEventLoop()
                    timer.timeout.connect(loop.quit)
                    loop.exec_()
            
            # Resetar formato da barra de progresso
            self.progressBar.setFormat("%p%")
            
            # Mostrar mensagem de resultado
            if loaded_count > 0:
                QMessageBox.information(
                    self, "Sucesso",
                    f"Carregados {loaded_count} mosaicos de {selected_index} com sucesso.\n"
                    f"{failed_count} mosaicos não puderam ser carregados."
                )
            else:
                QMessageBox.warning(
                    self, "Aviso",
                    f"Nenhum mosaico de {selected_index} pôde ser carregado para o período selecionado.\n"
                    "Verifique se os mosaicos estão disponíveis na sua conta Planet Labs."
                )
            
            # Resetar a barra de progresso após 2 segundos
            QTimer.singleShot(2000, lambda: self.progressBar.setValue(0))
            
        except Exception as e:
            self.progressBar.setValue(0)
            self.progressBar.setFormat("%p%")
            QMessageBox.critical(self, "Erro", f"Erro ao carregar mosaicos de {selected_index}: {str(e)}")
            import traceback
            print(f"*** ERRO AO CARREGAR MOSAICOS {selected_index} ***")
            print(traceback.format_exc())

    def get_proc_param_for_index(self, index_name):
        """Retorna o parâmetro de processamento para o índice selecionado"""
        index_map = {
            "NDVI": "ndvi",
            "NDWI": "ndwi",
            "MSAVI2": "msavi2",
            "VARI": "vari",
            "MTVI2": "mtvi2",
            "CIR": "cir"
        }
        return index_map.get(index_name, "ndvi")  # Default para ndvi se não encontrado

    def _configure_index_rendering(self, layer, index_name):
        """Configura a renderização do índice com paleta de cores adequada"""
        from qgis.core import (QgsRasterShader, QgsColorRampShader, 
                            QgsSingleBandPseudoColorRenderer, QgsContrastEnhancement)
        from qgis.PyQt.QtGui import QColor
        
        shader = QgsRasterShader()
        color_ramp = QgsColorRampShader()
        color_ramp.setColorRampType(QgsColorRampShader.Interpolated)
        
        # Selecionar esquema de cores adequado ao índice
        if index_name == "NDVI":
            items = [
                QgsColorRampShader.ColorRampItem(-1, QColor(0, 0, 128), 'Água/Sombra'),
                QgsColorRampShader.ColorRampItem(-0.5, QColor(0, 0, 255), 'Água'),
                QgsColorRampShader.ColorRampItem(0, QColor(128, 128, 128), 'Nuvem/Solo'),
                QgsColorRampShader.ColorRampItem(0.2, QColor(240, 240, 170), 'Solo/Urbano'),
                QgsColorRampShader.ColorRampItem(0.4, QColor(150, 200, 0), 'Vegetação esparsa'),
                QgsColorRampShader.ColorRampItem(0.6, QColor(50, 180, 50), 'Vegetação moderada'),
                QgsColorRampShader.ColorRampItem(0.8, QColor(0, 100, 0), 'Vegetação densa'),
                QgsColorRampShader.ColorRampItem(1.0, QColor(0, 50, 0), 'Vegetação muito densa')
            ]
        elif index_name == "NDWI":
            items = [
                QgsColorRampShader.ColorRampItem(-1, QColor(240, 240, 170), 'Vegetação densa'),
                QgsColorRampShader.ColorRampItem(-0.5, QColor(190, 210, 255), 'Vegetação/Solo úmido'),
                QgsColorRampShader.ColorRampItem(0, QColor(120, 170, 255), 'Umidade moderada'),
                QgsColorRampShader.ColorRampItem(0.3, QColor(30, 90, 180), 'Água rasa'),
                QgsColorRampShader.ColorRampItem(0.5, QColor(0, 0, 128), 'Água profunda'),
                QgsColorRampShader.ColorRampItem(1.0, QColor(0, 0, 0), 'Água muito profunda')
            ]
        elif index_name == "MSAVI2":
            items = [
                QgsColorRampShader.ColorRampItem(-1, QColor(128, 128, 128), 'Não vegetação'),
                QgsColorRampShader.ColorRampItem(0, QColor(210, 180, 140), 'Solo exposto'),
                QgsColorRampShader.ColorRampItem(0.2, QColor(230, 230, 120), 'Vegetação muito esparsa'),
                QgsColorRampShader.ColorRampItem(0.4, QColor(173, 223, 107), 'Vegetação esparsa'),
                QgsColorRampShader.ColorRampItem(0.6, QColor(63, 191, 63), 'Vegetação moderada'),
                QgsColorRampShader.ColorRampItem(0.8, QColor(0, 128, 0), 'Vegetação densa'),
                QgsColorRampShader.ColorRampItem(1.0, QColor(0, 64, 0), 'Vegetação muito densa')
            ]
        elif index_name == "VARI":
            items = [
                QgsColorRampShader.ColorRampItem(-1, QColor(0, 0, 100), 'Valor mínimo'),
                QgsColorRampShader.ColorRampItem(-0.5, QColor(140, 140, 140), 'Não vegetação/Sombra'),
                QgsColorRampShader.ColorRampItem(0, QColor(200, 200, 160), 'Solo exposto'),
                QgsColorRampShader.ColorRampItem(0.2, QColor(245, 245, 122), 'Vegetação estressada'),
                QgsColorRampShader.ColorRampItem(0.4, QColor(170, 240, 110), 'Vegetação moderada'),
                QgsColorRampShader.ColorRampItem(0.6, QColor(50, 220, 50), 'Vegetação saudável'),
                QgsColorRampShader.ColorRampItem(1.0, QColor(0, 180, 0), 'Vegetação muito saudável')
            ]
        elif index_name == "MTVI2":
            items = [
                QgsColorRampShader.ColorRampItem(0, QColor(128, 128, 128), 'Não vegetação'),
                QgsColorRampShader.ColorRampItem(0.2, QColor(200, 200, 100), 'Vegetação mínima'),
                QgsColorRampShader.ColorRampItem(0.4, QColor(160, 220, 60), 'Vegetação esparsa'),
                QgsColorRampShader.ColorRampItem(0.6, QColor(80, 200, 40), 'Vegetação moderada'),
                QgsColorRampShader.ColorRampItem(0.8, QColor(20, 160, 20), 'Vegetação densa'),
                QgsColorRampShader.ColorRampItem(1.0, QColor(0, 100, 0), 'Vegetação muito densa')
            ]
        elif index_name == "CIR":
            # Para CIR, que é uma composição de bandas, usar uma paleta que destaque vegetação em vermelho
            items = [
                QgsColorRampShader.ColorRampItem(-1, QColor(0, 0, 0), 'Valor mínimo'),
                QgsColorRampShader.ColorRampItem(0, QColor(0, 0, 128), 'Água'),
                QgsColorRampShader.ColorRampItem(0.3, QColor(128, 128, 128), 'Urbano/Solo'),
                QgsColorRampShader.ColorRampItem(0.6, QColor(200, 100, 100), 'Vegetação esparsa'),
                QgsColorRampShader.ColorRampItem(1.0, QColor(255, 0, 0), 'Vegetação densa')
            ]
        else:
            # Esquema padrão grayscale para índices não reconhecidos
            items = [
                QgsColorRampShader.ColorRampItem(-1, QColor(0, 0, 0), 'Mínimo'),
                QgsColorRampShader.ColorRampItem(0, QColor(128, 128, 128), 'Médio'),
                QgsColorRampShader.ColorRampItem(1, QColor(255, 255, 255), 'Máximo')
            ]
        
        color_ramp.setColorRampItemList(items)
        shader.setRasterShaderFunction(color_ramp)
        
        # Criar o renderer
        renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1, shader)
        
        # Aplicar o renderer à camada primeiro - isso é o mais importante
        layer.setRenderer(renderer)
        
        # Tentar aplicar o contraste, mas com tratamento de erro
        try:
            # Método seguro que funciona em diferentes versões do QGIS
            # Em algumas versões, o contraste é aplicado diretamente na camada
            if hasattr(layer, 'setContrastEnhancement'):
                enhancement = QgsContrastEnhancement(layer.dataProvider().dataType(1))
                enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
                layer.setContrastEnhancement(enhancement)
            # Em outras versões, podemos tentar ajustar o contraste no renderizador
            # Mas isso é mais seguro de ignorar se não estiver disponível
            elif hasattr(renderer, 'setContrastEnhancement'):
                enhancement = QgsContrastEnhancement(layer.dataProvider().dataType(1))
                enhancement.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
                renderer.setContrastEnhancement(enhancement)
        except Exception as e:
            # Se falhar, não é crítico - a renderização básica de cores ainda funciona
            print(f"Aviso: Não foi possível aplicar o contraste de imagem: {str(e)}")
            # Registrar o erro para debug
            import traceback
            print(traceback.format_exc())
        
        # Garantir que a camada seja atualizada
        layer.triggerRepaint()

    def setup_custom_client(self, api_key):
        """Setup a custom API client if the Planet API library is not available"""
        # This is a placeholder for custom implementation if needed
        self.client = CustomPlanetClient(api_key)
    
    def clear_saved_api_key(self):
        """Limpar API Key salva nas configurações"""
        settings = QSettings()
        settings.remove("planet_plugin/api_key")
        self.apiKeyLineEdit.clear()
        self.is_api_key_valid = False
        self.client = None
        
        # Desativar abas
        self.tabWidget.setTabEnabled(1, False)
        self.tabWidget.setTabEnabled(2, False)
        self.tabWidget.setTabEnabled(3, False)
        
        QMessageBox.information(self, "Informação", "A API Key salva foi removida com sucesso.")
        
class CustomPlanetClient:
    """Wrapper simples para requisições diretas à API quando a biblioteca planet não está disponível"""
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.planet.com/data/v1"
        self.basemaps_url = "https://api.planet.com/basemaps/v1"
        self.headers = {"Authorization": f"api-key {api_key}"}
        
    def get_mosaics(self):
        """Retorna um objeto que permite iterar sobre mosaicos disponíveis"""
        return MosaicIterator(self)
        
    def get_mosaics_quads(self, mosaic_id):
        """Retorna um objeto que permite iterar sobre quadrantes de um mosaico"""
        return QuadIterator(self, mosaic_id)
        
    def quick_search(self, query_filter, item_types):
        """Realiza uma busca rápida por itens (imagens) com os filtros especificados"""
        return ItemSearchResult(self, query_filter, item_types)
        
    def get_item(self, item_type, item_id):
        """Retorna um item específico pelo tipo e ID"""
        return ItemGetter(self, item_type, item_id)

class MosaicIterator:
    """Iterador para mosaicos"""
    def __init__(self, client):
        self.client = client
        self.url = f"{client.basemaps_url}/mosaics"  # Usando a URL do basemaps
        
    def iterate(self):
        """Itera sobre os mosaicos disponíveis"""
        response = requests.get(
            self.url, 
            auth=(self.client.api_key, '')  # Usar o método auth que funcionou no teste
        )
        if response.status_code == 200:
            mosaics = response.json().get('mosaics', [])
            for mosaic in mosaics:
                yield mosaic
        else:
            # Em caso de erro, retornar lista vazia
            yield from []

class QuadIterator:
    """Iterador para quadrantes de um mosaico"""
    def __init__(self, client, mosaic_id):
        self.client = client
        self.mosaic_id = mosaic_id
        self.url = f"{client.base_url}/mosaics/{mosaic_id}/quads"
        
    def iterate(self):
        """Itera sobre os quadrantes de um mosaico"""
        response = requests.get(self.url, headers=self.client.headers)
        if response.status_code == 200:
            quads = response.json().get('items', [])
            for quad in quads:
                yield quad
        else:
            # Em caso de erro, retornar lista vazia
            yield from []

class ItemSearchResult:
    """Resultado de busca por itens"""
    def __init__(self, client, query_filter, item_types):
        self.client = client
        self.query_filter = query_filter
        self.item_types = item_types
        self.url = f"{client.base_url}/quick-search"
        
    def items_iter(self, limit=100):
        """Itera sobre os itens encontrados na busca"""
        # Converter filtros para o formato da API
        filter_dict = self._convert_filter(self.query_filter)
        
        payload = {
            "item_types": self.item_types,
            "filter": filter_dict,
            "_page_size": min(limit, 100)  # Planet limita a 100 itens por página
        }
        
        response = requests.post(self.url, headers=self.client.headers, json=payload)
        if response.status_code == 200:
            items = response.json().get('features', [])
            for item in items:
                # Converter para o formato esperado pela aplicação
                yield {
                    'id': item.get('id'),
                    'properties': item.get('properties', {})
                }
        else:
            # Em caso de erro, retornar lista vazia
            yield from []
            
    def _convert_filter(self, filter_obj):
        """Converte objeto de filtro para o formato JSON esperado pela API"""
        # Esta é uma implementação simplificada
        # Você precisará adaptá-la para os filtros específicos que usa
        if hasattr(filter_obj, 'get_config'):
            return filter_obj.get_config()
        
        # Implementação básica para os tipos de filtros que você usa
        # Isso é um esboço - precisará ser adaptado para seus filtros específicos
        return {
            "type": "AndFilter",
            "config": [
                {"type": "GeometryFilter", "field_name": "geometry", "config": {}},
                {"type": "DateRangeFilter", "field_name": "acquired", "config": {}},
                {"type": "RangeFilter", "field_name": "cloud_cover", "config": {}}
            ]
        }

class ItemGetter:
    """Obtém informações de um item específico"""
    def __init__(self, client, item_type, item_id):
        self.client = client
        self.item_type = item_type
        self.item_id = item_id
        self.url = f"{client.base_url}/item-types/{item_type}/items/{item_id}"
        
    def get(self):
        """Obtém os detalhes do item"""
        response = requests.get(self.url, headers=self.client.headers)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Erro ao obter item: {response.status_code} - {response.text}")