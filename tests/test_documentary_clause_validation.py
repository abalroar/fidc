import unittest

from services.documentary_clause_validation import validate_primary_clause


class DocumentaryClauseValidationTests(unittest.TestCase):
    def check(self, criterion, text, expected):
        result = validate_primary_clause(criterion, text)
        self.assertEqual(expected, result["valid"], result["reason"])
        self.assertIsInstance(result["reason"], str)

    def test_fee_governance_is_not_fee_rule(self):
        self.check("performance_fee", "Compete à Assembleia deliberar sobre criação ou aumento da Taxa de Performance, por 50% dos votos.", False)
        self.check("management_fee", "O quórum para alteração da Taxa de Gestão é 75% dos votos dos cotistas.", False)
        self.check("performance_fee", "Não serão cobradas dos Cotistas taxa de performance, taxa de ingresso ou taxa de saída.", True)
        self.check("performance_fee", "O Fundo não possui taxa de ingresso, taxa de saída, e taxa de desempenho ou de performance.", True)
        self.check("performance_fee", "A Gestora fará jus à Taxa de Performance correspondente a 20% da valorização das Cotas Subordinadas Juniores que exceder CDI + 5%.", True)

    def test_allocation_rejects_other_denominators_and_generic_fidc_definition(self):
        self.check("allocation", "As CCBs deverão contar com garantias reais em montante mínimo de 50% do saldo devedor dos Direitos Creditórios.", False)
        self.check("allocation", "Fundos de investimento que apliquem mais de 50% de seu patrimônio líquido em direitos creditórios são FIDCs.", False)
        self.check("allocation", "Cotistas titulares de no mínimo 5% das cotas emitidas poderão convocar assembleia para alteração da política de investimento.", False)
        self.check("allocation", "Decorridos 180 dias, a Classe deverá manter no mínimo 51% do Patrimônio Líquido em Direitos Creditórios do Agronegócio.", True)
        self.check("allocation", '"Alocação Mínima": percentual mínimo de 50% do patrimônio líquido a ser mantido em Direitos Creditórios.', True)

    def test_receivable_nature_is_specific_to_acquired_credit(self):
        self.check("receivables", "4.14 A Classe poderá receber imóveis e outros Ativos Recuperados por execução das garantias.", False)
        self.check("receivables", "O Fundo destina seus recursos preponderantemente à aquisição de Direitos Creditórios Elegíveis conforme Anexo Descritivo.", False)
        self.check("receivables", "Os Direitos Creditórios são representados por CCBs decorrentes de empréstimos consignados em folha de empregados de empresas privadas.", True)

    def test_eligibility_requires_conditions_after_3rd_regulation_introduction(self):
        intro = "8.2.1 A Classe somente poderá adquirir os Direitos Creditórios que atendam, cumulativamente, aos Critérios de Elegibilidade, na respectiva Data de Aquisição."
        list_intro = "10.1 A Classe somente poderá adquirir Direitos Creditórios que atendam aos seguintes Critérios de Elegibilidade, a serem verificados pela Gestora, de forma definitiva, na respectiva Data de Aquisição:"
        self.check("eligibility", intro, False)
        self.check("eligibility", list_intro, False)
        self.check("eligibility", intro + "\n\n" + list_intro, False)
        self.check("eligibility", list_intro + " (i) prazo de vencimento inferior a 360 dias; (ii) Direitos Creditórios adimplentes, sem parcelas vencidas.", True)
        self.check("eligibility", "Os Direitos Creditórios elegíveis deverão ser representados por CCBs regularmente emitidas por pessoas físicas e não poderão estar inadimplentes.", True)
        self.check("eligibility", list_intro + " (i) os Direitos Creditórios deverão estar formalizados por documentos comprobatórios; (ii) os devedores devem ser pessoas jurídicas.", True)
        self.check("eligibility", list_intro + " (i) ser emitidas por pessoa jurídica de qualquer natureza, inclusive sociedades por ações e limitadas.", True)
        self.check("eligibility", "O Custodiante verificará em até 2 dias úteis se os Direitos Creditórios atendem aos Critérios de Elegibilidade na respectiva Data de Aquisição.", False)

    def test_provider_conflict_does_not_identify_originator_or_debtor(self):
        conflict = "4.4.3 Os prestadores de serviços subcontratados pelo Custodiante não poderão ser, em relação ao Fundo, originador, Cedente, Gestora, Consultoria especializada ou partes a eles relacionadas."
        self.check("originator", conflict, False)
        self.check("debtor", "Os prestadores subcontratados pelo Custodiante não poderão ser devedores ou empresas relacionadas aos sacados.", False)
        self.check("originator", conflict + " Os Cedentes serão pessoas jurídicas com operações de venda mercantil.", True)
        self.check("originator", '"Cedente" significa Empresa Mercantil S.A., CNPJ 12.345.678/0001-99.', True)
        self.check("originator", "Os Cedentes deverão ser instituições financeiras autorizadas a conceder empréstimos consignados.", True)
        self.check("debtor", "Os Devedores serão pessoas físicas aposentadas e pensionistas do INSS, titulares dos empréstimos consignados.", True)
        self.check("originator", "É vedada a subcontratação pela Administradora de Cedentes relacionados ao Gestor. Os direitos creditórios serão originados pelo Banco Exemplo S.A., CNPJ 12.345.678/0001-99.", True)
        self.check("debtor", "Os prestadores subcontratados pelo Custodiante não poderão ser devedores. Os direitos creditórios serão originados pelo Banco Exemplo S.A., CNPJ 12.345.678/0001-99.", False)

    def test_debtor_rejects_actual_incidental_v7_answers(self):
        # Current primary documents: 1218996/1219005/1239751/982232/
        # 1002580/1199536/1222863/1322406. A person type nearby is not identity.
        rejected = [
            "Monitoramento de Grupos Econômicos – Os desempenhos econômico e financeiro de empresas são potencialmente afetados por eventos referentes a outras empresas pertencentes a seus Grupos Econômicos. A Gestora busca informações que permitam identificar se os Cedentes e/ou os Devedores pertencem aos mesmos Grupos Econômicos e gerenciar os Direitos Creditórios detidos pelo Fundo.",
            "XX. Movimentação das contas dos Devedores junto ao FGTS: quando da Cessão Fiduciária em garantia dos Direitos Creditórios Saque-Aniversário, parte do saldo que o respectivo Devedor possui em sua conta junto ao FGTS é bloqueada. Caso o Devedor tenha idade igual ou superior a 70 anos, se aposente ou faleça, o saque poderá ser realizado antecipadamente.",
            "Significa o Banco Central do Brasil. ‘BACEN’. Significam, quando mencionadas em conjunto, a CPX e a ITR. ‘Cedentes’. Significa o Cadastro Nacional da Pessoa Jurídica do Ministério da Fazenda. ‘CNPJ’. A Conta da Classe receberá os créditos pagos pelos Devedores.",
            "15.1.4 Riscos específicos (i) Risco do Empregador se tornar insolvente: o pagamento dos Direitos Creditórios pelos Devedores está diretamente ligado ao recebimento, pelos Devedores, de remuneração decorrente do vínculo empregatício mantido junto aos Empregadores. Caso o Empregador se torne insolvente e suspenda a remuneração, o Devedor poderá ficar inadimplente.",
            "Necessidade de cobrança extrajudicial e judicial dos Direitos Creditórios Adquiridos. Caso a Consignação não seja realizada pelo INSS, é possível que seja necessário cobrar judicial ou extrajudicialmente os Direitos Creditórios Inadimplidos diretamente dos Devedores, causando prejuízo ao Fundo.",
            "5.5 Os documentos do checklist jurídico e cadastral são os seguintes: (iii) cópia do RG ou Carteira Nacional de Habilitação para os Devedores pessoa física ou cópia do contrato/estatuto social para os Devedores pessoa jurídica, podendo ser obtidos pela Solfácil via API; (iv) comprovante de residência do Devedor pessoa física.",
            "(iii) manter e operar um serviço de atendimento ao consumidor - SAC e uma ouvidoria, monitorar e resolver reclamações e solicitações de Devedores com relação às operações de empréstimo consignado que dão origem aos Direitos Creditórios, em conformidade com o Acordo de Parceria.",
            "O valor dos Direitos Creditórios devidos por Devedores pessoas jurídicas não poderá ser superior a 25% do PL; a concentração em cada Devedor pessoa física fica limitada a 2% do PL.",
            "(xvi) a idade dos Devedores pessoas físicas, na emissão da respectiva CCB, deve ser de no máximo 71 anos.",
            "Os Direitos Creditórios devem ter sido formalizados por emissão, pelos Devedores, de CCBs em favor da Instituição Financeira Parceira; o Devedor não deve estar inadimplente.",
        ]
        for text in rejected:
            with self.subTest(text=text[:80]):
                self.check("debtor", text, False)

    def test_debtor_preserves_positive_glossaries_and_loan_population(self):
        accepted = [
            '“Devedores” Pessoas que celebraram Contratos de Empréstimo com consignação em folha de pagamento/benefício.',
            'Significam os devedores (sacados), pessoas físicas “Devedores” ou jurídicas, que tenham estabelecido relação de consumo dos Direitos Creditórios com as Cedentes.',
            '“Devedores” Significam os devedores (sacados), pessoas físicas ou jurídicas, que tenham estabelecido relação de consumo dos Direitos Creditórios com as Cedentes.',
            '“Devedores”: cada pessoa física que possua vínculo empregatício registrado na CTPS digital, verificado e validado pela Dataprev na categoria101 do eSocial, que tenha tomado um empréstimo consignado mediante emissão eletrônica de CCB.',
            '“Devedores” Em conjunto, Devedores – Empréstimo Consignado e os Devedores – Cartão INSS. “Devedor – Cartão INSS” Cada pessoa física titular de Benefícios que assinou a Proposta de Adesão e tomou crédito com a Facta mediante saque com utilização de Cartão INSS, com Consignação na respectiva folha de Benefícios.',
            'Devedores (sacados): pessoas físicas ou jurídicas com sede no país, de créditos nos segmentos industrial, comercial, agronegócio, financeiro e prestação de serviços.',
            'A Classe adquire títulos de crédito podendo serem devidos por pessoas físicas ou jurídicas com sede no país.',
            '4.4 Os Direitos Creditórios Consignado Privado são originados no âmbito de operações de empréstimo consignado concedido pelo Endossante a um Devedor por meio da Plataforma MT e representado por CCB eletrônica. O pagamento regular dos créditos é feito por Consignação.',
            'Devedores de consignado privado: tomadores de empréstimos concedidos pelo Endossante, processados pela Plataforma MT, representados por CCB eletrônica e pagos por desconto em folha.',
            'A Solfácil avalia o risco financeiro do Devedor para instruir a Instituição Financeira Parceira a liberar um Financiamento Solar. II. Análise de Crédito do Tomador (i) para Devedores pessoa física: ausência de irregularidades financeiras; (ii) Para Devedores pessoa jurídica: análise de endividamento.',
            'Devedores tomadores de Financiamento Solar: pessoas físicas e pessoas jurídicas, avaliadas separadamente na política de concessão de crédito.',
            'Os contratos de crédito são firmados entre os estudantes (Devedores) e as Instituições de Ensino Superior.',
            'Os Devedores dos Direitos Creditórios devem ser pessoas físicas ou jurídicas inscritas no CPF ou CNPJ.',
            '“Devedor(es)” significam as pessoas jurídicas, clientes dos Cedentes, que tenham realizado locação de Equipamentos.',
            'Os Devedores são Empresa Comercial S.A., CNPJ 12.345.678/0001-99.',
            '“Devedores” Significa qualquer pessoa jurídica com sede no Brasil, integrante do Grupo Saga, que tenha emitido as Notas Comerciais subscritas.',
            '“Devedores” Significam, (i) no caso das CPR-F, os produtores rurais, pessoas físicas e/ou jurídicas e cooperativas de produtores rurais, indicados pelo Originador.',
            'Serão considerados Devedores: (i) dos Direitos Creditórios Cedente, os produtores rurais, pessoas físicas e/ou jurídicas; (ii) dos Direitos Creditórios LF, as Instituições Financeiras Autorizadas que emitiram Letras Financeiras.',
            'Os Direitos Creditórios deverão ser representados por CCB cujos Devedores sejam exclusivamente pessoas físicas.',
            'O Direito Creditório deve ser devido por pessoas físicas titulares de contas vinculadas do FGTS que tenham a opção Saque Aniversário vigente na contratação.',
            '“Devedores” significam os emissores, devedores e/ou garantidores dos Direitos Creditórios, conforme o caso. Para fins da Classe, serão, exclusivamente, as seguintes Credenciadoras: (i) Cielo S.A., inscrita no CNPJ nº01.027.058/0001-91.',
        ]
        for text in accepted:
            with self.subTest(text=text[:80]):
                self.check("debtor", text, True)

    def test_debtor_keeps_positive_rule_separate_from_incidental_context(self):
        self.check("debtor", '“Devedores” Pessoas que contrataram empréstimos consignados. O risco do Empregador pode afetar a remuneração e os pagamentos dos Devedores.', True)
        self.check("debtor", 'Os Devedores serão atendidos pela Empresa Serviços S.A., CNPJ12.345.678/0001-99, em um SAC para reclamações e ouvidoria.', False)
        self.check("debtor", 'Os direitos creditórios serão originados pelo Banco Exemplo S.A., CNPJ12.345.678/0001-99. Os pagamentos pelos Devedores podem atrasar e impactar as cotas.', False)
        self.check("debtor", 'A política de cadastro coleta documentos para Devedores pessoas físicas ou jurídicas; a análise de crédito do tomador coleta cópia do RG para liberar um financiamento solar.', False)

    def test_allocation_does_not_promote_mt_inss_vi_retention_salary(self):
        # Regulamento 1153514, physical page 34, recovered by Apple Vision OCR.
        salary = """Remuneração do Agente de Retenção/Cobrança
        Pelos serviços de retenção e cobrança, prestada nos termos deste Anexo e do Contrato de Retenção e Cobrança,
        será devida pela Classe ao Agente de Retenção e Cobrança remuneração mensal correspondente a um
        percentual de, no mínimo, 0,25% (vinte e cinco décimos por cento) ao ano limitado a 3% (três por cento) ao
        ano, cujo detalhamento da aplicação do percentual será descrito no Contrato de Retenção e Cobrança,
        observado o cumprimento da Taxa Mínima de Endosso de cada operação, incidente sobre o Patrimônio Líquido
        alocado em Direitos Creditórios."""
        self.check("allocation", salary, False)
        self.check("allocation", "A Classe deverá remunerar o Agente em no mínimo 0,25% sobre o Patrimônio Líquido alocado em Direitos Creditórios.", False)
        self.check("allocation", salary + " A Classe deverá manter, no mínimo, 50% do Patrimônio Líquido em Direitos Creditórios após 180 dias.", True)
        self.check("allocation", salary + " A Classe deverá manter a reserva para remuneração do Agente. No mínimo 50% do PL alocado em Direitos Creditórios será base da cobrança.", False)
        self.check("allocation", "Decorridos 180 dias, a Classe deverá aplicar no mínimo 50,0% do PL em Direitos Creditórios. A remuneração do Gestor será 0,25% ao ano.", True)

    def test_receivables_does_not_promote_mt_inss_vi_file_tasks(self):
        # Regulamento 1153514, OCR page 30: operating duties and file titles.
        tasks = """11.10 Incluem-se entre as obrigações do Gestor:
        (iv) receber o Arquivo de Bloqueio do Endossante MT, realizar sua análise e seleção e decidir sobre a
        aquisição ou rejeição, pela Classe, dos Direitos Creditórios nele listados, observando estritamente as
        regras relativas à política de investimento, composição e diversificação da Carteira;
        (v) preparar e fornecer aos Cotistas e ao Agente de Retenção/Cobrança, até o 10º Dia Útil, Relatório de Performance;
        (vi) preparar o Arquivo de Financiamento, calcular o Preço de Aquisição e preparar o respectivo Termo de Endosso das CCBs."""
        self.check("receivables", tasks, False)
        self.check("receivables", "O Agente deverá receber o Arquivo de Bloqueio das CCBs e fornecer Relatório de Performance dos contratos de financiamento.", False)
        self.check("receivables", tasks + " Os Direitos Creditórios são representados por CCBs eletrônicas decorrentes de empréstimos consignados com pagamento pelo INSS e Dataprev.", True)
        self.check("receivables", "As CCBs representam parcelas vincendas de empréstimos consignados prefixados. O Gestor deverá preparar o Arquivo de Financiamento.", True)
        self.check("receivables", "A Classe poderá adquirir empréstimos consignados de beneficiários do INSS; o Gestor deverá receber o Arquivo de Bloqueio.", True)

    def test_provider_role_needs_identity(self):
        self.check("providers", "A Administradora, a Gestora e o Custodiante não serão responsáveis por prejuízos de medidas judiciais do Fundo.", False)
        self.check("providers", "Os cotistas titulares de 5% podem convocar representantes da administradora, gestora e custodiante.", False)
        self.check("providers", "O Fundo é administrado pela BTG Pactual Serviços Financeiros S.A., inscrita no CNPJ 59.281.253/0001-23. O custodiante é Banco BTG Pactual S.A.", True)

    def test_rating_of_investee_or_debtor_is_separate(self):
        self.check("rating", "Os ativos de liquidez de emissão de instituições financeiras deverão ter rating AA do devedor.", False)
        self.check("rating", "As cotas de outros fundos investidos deverão possuir classificação de risco AAA.", False)
        self.check("rating", "O Gestor poderá contratar serviços de intermediação, agência de classificação de risco e consultoria.", False)
        self.check("rating", "As Cotas Seniores serão avaliadas trimestralmente pela Fitch Ratings. O rebaixamento em 2 níveis constitui Evento de Avaliação.", True)
        self.check("rating", "Não haverá classificação de risco das Cotas Seniores, salvo se requerida por titulares de ao menos 50% dessas cotas.", True)

    def test_credit_guarantees_are_not_investment_warnings(self):
        self.check("guarantee", "As aplicações no Fundo não contam com garantia da Administradora, Gestora ou FGC.", False)
        self.check("guarantee", "As Cotas Subordinadas Júnior não podem ser objeto de penhor ou alienação fiduciária de obrigações dos seus titulares.", False)
        self.check("guarantee", "As CCBs deverão contar com cessão fiduciária de recebíveis devidamente constituída e Devedor Solidário para principal inferior a R$100.000.", True)
        self.check("guarantee", "Os créditos da carteira não contam com garantias reais do Devedor.", True)

    def test_quota_payment_is_not_debtor_payment_or_capital_call(self):
        self.check("payments", "A data de vencimento da primeira parcela dos direitos creditórios deve ocorrer em até 365 dias após aquisição.", False)
        self.check("payments", "Os cotistas deverão integralizar as cotas em até 5 dias úteis após cada chamada de capital.", False)
        self.check("payments", "O suplemento deverá conter as seguintes informações das Cotas Seniores: quantidade, valor nominal e cronograma de amortização.", False)
        self.check("payments", "As Cotas Seniores serão amortizadas mensalmente no 10º Dia Útil; os juros serão pagos mensalmente durante a carência de 12 meses.", True)

    def test_headers_and_remissions_are_not_answer(self):
        self.check("providers", "I. DEFINIÇÕES ................. 7 II. PRESTADORES DE SERVIÇOS ................. 12", False)
        self.check("performance_fee", "TAXA DE PERFORMANCE", False)
        self.check("payments", "Cronograma de amortização conforme o Apêndice da Subclasse.", False)
        self.check("changes", "O Regulamento poderá ser alterado independentemente de Assembleia para atendimento a normas legais.", False)
        self.check("changes", "A Assembleia aprovou a alteração do item 4.2 do Regulamento, que passa a vigorar com nova redação para reserva de caixa.", True)

    def test_specialized_legacy_questions_preserve_their_perimeter(self):
        self.check("quota_grace", "Os contratos de empréstimo dos devedores terão carência de 6 meses.", False)
        self.check("quota_grace", "As Cotas Seniores terão carência de principal de 12 meses contados da primeira integralização.", True)
        self.check("quota_maturity", "Cada CCB terá prazo de vencimento de no máximo 360 dias.", False)
        self.check("quota_maturity", "O vencimento final das Cotas Seniores ocorrerá em 20/12/2030.", True)
        self.check("quota_classes", "Classe de cotas única.", True)
        self.check("quota_classes", "As Cotas da classe são divididas nas Subclasses Sênior, Mezanino e Subordinada Júnior.", True)
        self.check("duration_investors", "O Fundo é constituído por prazo indeterminado e destina-se exclusivamente a investidores profissionais.", True)
        self.check("duration_investors", "Os direitos creditórios deverão ter prazo máximo de 360 dias.", False)
        self.check("offers", "ANÚNCIO DE ENCERRAMENTO: 1ª emissão de cotas, registro CVM/SRE/AUT/FDC/PRI/2026/123.", True)
        self.check("legacy_events", "São Eventos de Avaliação: índice de inadimplência acima de 10% por dois dias úteis consecutivos.", True)

    def test_event_lists_and_risk_warnings_do_not_answer_operational_questions(self):
        event = '11.1 As seguintes hipóteses são consideradas Eventos de Avaliação: (i) renúncia do Agente da Conta Vinculada; (ii) falência do Custodiante; (iii) não entrega pelo Devedor dos documentos comprobatórios.'
        self.check('collection_account',event,False)
        self.check('debtor',event,False)
        self.check('providers',event+' O administrador Banco Exemplo S.A., CNPJ 12.345.678/0001-99.',False)
        self.check('replacement','11.2 As seguintes hipóteses são Eventos de Liquidação: renúncia do Administrador sem sua substituição.',False)
        self.check('cross_default','A validade da cessão poderá ser questionada em decorrência da falência ou recuperação judicial dos cedentes, afetando o Fundo.',False)
        self.check('cross_default','Constitui Evento de Avaliação a intervenção ou liquidação extrajudicial do Endossante.',True)
        self.check('audit','Quando do encerramento e liquidação da Classe, auditor independente deverá emitir parecer técnico das demonstrações contábeis.',False)
        self.check('audit','As demonstrações contábeis do Fundo serão auditadas anualmente pelo Auditor Independente.',True)
        self.check('replacement','A Administradora e a Gestora deverão ser substituídas em caso de descredenciamento, renúncia ou destituição pela Assembleia.',True)
        self.check('collection_account','Os Direitos Creditórios serão pagos por TED em conta de titularidade do Fundo, em Conta Vinculada ou conta do Cedente para posterior transferência à conta do Fundo.',True)

    def test_global_sample_templates_and_unrelated_fields_are_rejected(self):
        self.check('waterfall','Montante das Cotas R$ [●]. Quantidade [●]. Observada a ordem de alocação de recursos no Regulamento, as Cotas terão amortização mensal.',False)
        self.check('waterfall','O Anexo de cada classe de cotas dispõe, sem prejuízo dos demais requisitos, sobre as respectivas: (i) características; (ii) ordem de alocação de recursos; (iii) reservas.',False)
        self.check('waterfall','17.2 Observada a ordem de alocação de recursos prevista no CAPÍTULO 11, a Administradora deverá manter reserva de liquidez equivalente a 2,50% do PL.',False)
        self.check('waterfall','Os recursos observarão a seguinte ordem de alocação de recursos: (i) pagamento de despesas; (ii) reserva de liquidez; (iii) amortização das Cotas Seniores.',True)
        self.check('waterfall','15.1.7 Riscos decorrentes do Regime de Amortização das Cotas (i) Risco decorrente da ordem de alocação das distribuições: conforme previsto no Anexo, as Cotas serão amortizadas de acordo com a ordem de alocação prevista no Capítulo 7.',False)
        self.check('pdd','Todo Dia Útil, após provisionamento das despesas e encargos, será incorporado ao valor de cada Cota Sênior a valorização limitada ao Benchmark Sênior.',False)
        self.check('pdd','A provisão de perdas dos Direitos Creditórios será calculada por faixa de atraso: 31 a 60 dias, 3% do valor de cada crédito.',True)
        self.check('receivables','Os Direitos Creditórios serão adquiridos de acordo com a política de investimento abaixo, observadas as condições do Contrato de Cessão.',False)
        self.check('providers','O Depositário notificará o Custodiante para confirmar a operação, e o Banco Depositário fará a transferência no vencimento dos créditos.',False)
        self.check('guarantee','Questionamento da validade e eficácia da cessão dos Direitos Creditórios. Principais eventos que podem afetar a cessão: existência de garantias reais constituídas antes da cessão sem conhecimento do Fundo.',False)

    def test_global_residuals_keep_material_roles_and_credit_nature(self):
        self.check('providers','Revisão das demonstrações e atuação da Administradora: (a) PriceWaterhouse Coopers Auditores Independentes; (b) Deloitte Brasil Auditores Independentes Ltda.',False)
        self.check('providers','Agência Classificadora de Risco: escolhida pela Gestora e ratificada pela Administradora dentre Standard & Poor’s Ratings do Brasil Ltda., Fitch Ratings Brasil Ltda. ou Moody’s América Latina Ltda.',False)
        self.check('providers','4.1.1 O Fundo é administrado pelo GENIAL INVESTIMENTOS CORRETORA DE VALORES MOBILIÁRIOS S.A., CNPJ 27.652.684/0001-62.',True)
        self.check('providers','4.2.1 O Fundo é gerido pela GENIAL GESTÃO LTDA., CNPJ 22.119.959/0001-83.',True)
        self.check('receivables','Após a originação do crédito e celebrado o Contrato de Financiamento, o Cedente poderá ofertar os Direitos Creditórios para aquisição pelo Fundo, observado procedimento de elegibilidade e condições de cessão.',False)
        self.check('receivables','Risco de Originação: os Direitos Creditórios a serem adquiridos pelo Fundo são decorrentes de financiamentos estudantis destinados ao pagamento de serviços educacionais.',True)
        self.check('guarantee','(a) existência de garantias reais sobre os Direitos Creditórios, ocorridas antes da sua cessão ao Fundo e sem o conhecimento do Fundo;',False)
        self.check('pdd','Em 31/12/2025, a Classe detinha R$96.585 mil líquidos de provisão para perdas estimadas, 57,55% do PL, mensurados com base na metodologia descrita na nota explicativa nº3.',False)
        self.check('pdd','A Gestora poderá renegociar os direitos creditórios com desconto limitado ao montante da PDD reconhecida.',False)
        self.check('pdd','Conforme nota explicativa nº3, a provisão é calculada por faixa de atraso: de31a60dias,3% de cada crédito; acima de180dias,100%.',True)
        self.check('pdd','2025Faixas de Vencimento: A Vencer, Vencido, Totais; de0a30dias,105.495,6.674,112.169;(-)Provisão para perdas por redução no valor de recuperação(450); Direitos creditórios líquidos da provisão140.372.',False)
        self.check('pdd','No exercício findo em31/03/2025, a Administradora realizou provisão para perdas por redução no valor de recuperação dos créditos no montante deR$450mil.',False)
        self.check('pdd','Até30dias de atraso não haverá provisão; após31dias será provisionado1/60do valor presente do crédito por dia até90dias; após90dias,100%.',True)

    def test_essential_provider_and_investee_roles_are_explicit(self):
        self.check('providers','O Advance Rate Ponderado será calculado pelo Gestor com base no Valor Agregado dos Direitos Creditórios. A agência de risco poderá ser escolhida dentre Austin Rating Serviços Financeiros Ltda., Fitch Ratings Brasil Ltda. ou Moody’s América Latina Ltda.',False)
        self.check('providers','Os Prestadores de Serviços Essenciais Pré-Aprovados para substituição poderão ser: Banco Genial S.A., para a função de administradora; Genial Gestão Ltda., para a função de gestora.',False)
        self.check('providers','"Gestor" significa a POLÍGONO CAPITAL LTDA., inscrita no CNPJ 43.241.789/0001-85, autorizada à prestação do serviço de gestão de carteiras de valores mobiliários.',True)
        self.check('providers','4.1 A administração fiduciária do Fundo será realizada pelo BANCO DAYCOVAL S.A., inscrito no CNPJ 62.232.889/0001-90.',True)
        self.check('providers','Gestora A VIA INVEST GESTORA DE RECURSOS LTDA., inscrita no CNPJ 44.141.694/0001-52, autorizada à atividade de gestão.',True)
        self.check('providers','Como gestora da Carteira do Fundo foi contratada a Polígono Capital Ltda., CNPJ 43.241.789/0001-85.',True)
        self.check('providers','O Custodiante poderá contratar a Serasa Experian S.A. e a Gestora efetuará a cobrança de devedores após10dias.',False)
        self.check('providers','Aos Cotistas e ao Administrador\nGonn Fundo de Investimento em Direitos Creditórios\n(Administrado pelo Banco Genial S.A.)',True)
        self.check('providers','Ativos: recebíveis de cartão.\nAdministradora BEM Distribuidora de Títulos e Valores Mobiliários Ltda.\nCustodiante Banco Bradesco S.A.',True)
        self.check('providers','BANCO DAYCOVAL S.A., instituição financeira autorizada pela CVM, CNPJ62.232.889/0001-90.\nADMINISTRADORA do BV AUTO III FIDC.',True)
        self.check('investee','11.1 São considerados Eventos de Avaliação: os itens poderão ser verificados pelo Administrador e/ou Gestor; não pagamento das Cotas Subordinadas Mezanino em 2 dias úteis.',False)
        self.check('investee','A Reserva para Despesas será constituída com recursos recebidos dos pagamentos dos Direitos Creditórios, em montante de1,05% do Patrimônio Líquido do Fundo para proteção das cotas da Classe.',False)
        self.check('investee','A carteira deverá manter 67% do patrimônio líquido em Direitos Creditórios para fins fiscais; os rendimentos das cotas do Fundo serão tributados à alíquota de15%.',False)
        self.check('investee','O Fundo deverá investir no mínimo95% do patrimônio líquido em cotas de fundos de investimento em direitos creditórios, inclusive cotas subordinadas mezanino de classes investidas.',True)
        self.check('investee','É vedado à Classe investir em cotas de outros fundos de investimento ou de outras classes.',True)

    def test_event_headings_responsibilities_and_cure_procedures_need_trigger(self):
        for criterion in ('evaluation','liquidation','legacy_events'):
            self.check(criterion,'11.1 São considerados Eventos de Avaliação do Fundo quaisquer das seguintes ocorrências, observado que os subitens(i),(ii),(iii) serão verificados pelo Administrador e os subitens(iv),(v) pelo Gestor.',False)
            self.check(criterion,'No caso de a Assembleia deliberar que qualquer Evento de Avaliação constitui Evento de Liquidação, o Administrador observará os procedimentos do item11.2 sem convocação de nova Assembleia.',False)
        self.check('evaluation','11.1 São considerados Eventos de Avaliação do Fundo: (i) não observância do prazo de180dias para alcançar a alocação mínima; (ii) não realização de pagamento das Cotas Seniores em até2dias úteis.',True)
        self.check('liquidation','Constitui Evento de Liquidação a recuperação judicial ou falência do Cedente e a não substituição do Custodiante em60dias.',True)
        self.check('legacy_events','São Eventos de Avaliação: índice de inadimplência acima de10% por dois dias úteis consecutivos.',True)
        self.check('legacy_events','14.3 Não haverá Eventos de Liquidação Antecipada Adicionais.',True)
        self.check('liquidation','Na hipótese de não instalação da Assembleia Especial, em segunda convocação por falta de quórum, o Evento de Avaliação constituirá Evento de Liquidação.',True)


if __name__ == "__main__":
    unittest.main()
