# Reconciliação do Dataset

## Resumo executivo

- Registros Python antes da reconciliação: **1106**.
- Registros Power Query: **1076**.
- Registros Python após a reconciliação: **1076**.
- Registros somente Python antes das regras: **30**.
- Registros somente Power Query antes das regras: **0**.
- Registros exclusivos restantes no Python: **0**.
- Registros exclusivos restantes no Power Query: **0**.
- Grupos de Nota Fiscal duplicada no Python: **3**.
- Grupos de CTe repetido no Python: **99**.
- Critério de aceitação: **ATENDIDO**.

Todas as ocorrências excedentes vieram do Excel bruto do Active; nenhuma foi criada pelo transformador.

## Possíveis causas observadas

- Destinatário e Tomador representam a mesma parte: **17** ocorrência(s).
- Saída não preenchida: **17** ocorrência(s).
- Tipo CTe não pertence aos tipos mantidos pela referência: **12** ocorrência(s).
- Fatura preenchida sem aprovação financeira: **2** ocorrência(s).
- Cancelamento preenchido: **2** ocorrência(s).
- Evidência textual de devolução: **13** ocorrência(s).
- Tipo complementar: **1** ocorrência(s).
- Nota Fiscal repetida: **3** ocorrência(s).
- CTe repetido: **2** ocorrência(s).
- Redespacho preenchido: **21** ocorrência(s).

## Hipóteses confirmadas

- Tipos de documento inferidos das notas mantidas: entrega normal, reentrega
- Somente registros com Saída preenchida permanecem.
- Registros em que Destinatário e Tomador são a mesma parte são removidos.
- Registros faturados sem aprovação financeira são removidos.

## Hipóteses descartadas

- Emissão não explica a diferença: as mesmas datas aparecem nos dois conjuntos.
- Redespacho não explica a diferença: há registros com redespacho mantidos.
- Cancelamento isolado não é necessário para reproduzir o conjunto final.
- Deduplicação isolada não é necessária para reproduzir o conjunto final.

## Duplicidades por Nota Fiscal — Python

| Campo | Valor | Ocorrências | Linhas do Excel |
|---|---|---:|---|
| Nota Fiscal | 1019059 | 2 | 167, 1107 |
| Nota Fiscal | 1019765 | 2 | 543, 1097 |
| Nota Fiscal | 226752 | 2 | 542, 1091 |

## Duplicidades por Nota Fiscal — Power Query

Nenhuma duplicidade encontrada.

## Duplicidades por CTe — Python

| Campo | Valor | Ocorrências | Linhas do Excel |
|---|---|---:|---|
| CTe | 1012852 | 4 | 771, 772, 773, 774 |
| CTe | 1012856 | 2 | 899, 900 |
| CTe | 1012862 | 2 | 255, 256 |
| CTe | 14199844 | 2 | 883, 884 |
| CTe | 14200973 | 2 | 147, 148 |
| CTe | 14200976 | 3 | 514, 515, 516 |
| CTe | 14200978 | 2 | 971, 972 |
| CTe | 1731382 | 2 | 71, 72 |
| CTe | 1731391 | 2 | 274, 275 |
| CTe | 1731443 | 2 | 304, 305 |
| CTe | 1731445 | 2 | 306, 307 |
| CTe | 1731446 | 3 | 962, 963, 964 |
| CTe | 1756758 | 2 | 476, 477 |
| CTe | 2158948 | 2 | 263, 264 |
| CTe | 2158965 | 2 | 331, 332 |
| CTe | 2161707 | 2 | 341, 342 |
| CTe | 2161709 | 2 | 1015, 1016 |
| CTe | 2365556 | 2 | 21, 23 |
| CTe | 2365558 | 2 | 870, 871 |
| CTe | 2365561 | 5 | 61, 62, 63, 64, 65 |
| CTe | 2365565 | 2 | 655, 656 |
| CTe | 2367475 | 2 | 471, 472 |
| CTe | 2367482 | 2 | 708, 709 |
| CTe | 2920327 | 2 | 1106, 1107 |
| CTe | 6285032 | 4 | 857, 858, 859, 860 |
| CTe | 6285047 | 2 | 212, 213 |
| CTe | 6285050 | 3 | 221, 222, 223 |
| CTe | 6285051 | 2 | 629, 630 |
| CTe | 6285062 | 2 | 639, 640 |
| CTe | 6285069 | 2 | 775, 776 |
| CTe | 6285079 | 2 | 855, 856 |
| CTe | 6285080 | 2 | 644, 645 |
| CTe | 6285085 | 3 | 13, 14, 15 |
| CTe | 6285088 | 2 | 408, 409 |
| CTe | 6285097 | 2 | 59, 60 |
| CTe | 6285108 | 2 | 650, 651 |
| CTe | 6285846 | 2 | 68, 69 |
| CTe | 6285847 | 2 | 243, 244 |
| CTe | 6285866 | 3 | 27, 28, 29 |
| CTe | 6285869 | 3 | 246, 247, 248 |
| CTe | 6286312 | 4 | 938, 939, 940, 941 |
| CTe | 6286331 | 2 | 296, 297 |
| CTe | 6286339 | 2 | 497, 498 |
| CTe | 6286350 | 2 | 491, 492 |
| CTe | 6286352 | 2 | 493, 494 |
| CTe | 6286388 | 2 | 141, 142 |
| CTe | 6286980 | 4 | 986, 987, 988, 989 |
| CTe | 6286983 | 2 | 741, 742 |
| CTe | 6286992 | 2 | 748, 749 |
| CTe | 6286994 | 2 | 1067, 1068 |
| CTe | 6287030 | 2 | 324, 325 |
| CTe | 6287043 | 2 | 322, 323 |
| CTe | 76828 | 3 | 1035, 1036, 1037 |
| CTe | 76830 | 2 | 603, 604 |
| CTe | 76835 | 3 | 554, 555, 556 |
| CTe | 76836 | 3 | 575, 576, 577 |
| CTe | 76842 | 2 | 557, 558 |
| CTe | 76854 | 3 | 563, 564, 565 |
| CTe | 76855 | 2 | 583, 584 |
| CTe | 76864 | 2 | 183, 184 |
| CTe | 76866 | 2 | 808, 809 |
| CTe | 76867 | 2 | 812, 813 |
| CTe | 76876 | 2 | 1041, 1042 |
| CTe | 76878 | 2 | 571, 572 |
| CTe | 76880 | 2 | 1084, 1085 |
| CTe | 76881 | 3 | 578, 579, 580 |
| CTe | 76883 | 2 | 821, 822 |
| CTe | 76896 | 2 | 589, 590 |
| CTe | 76899 | 2 | 357, 358 |
| CTe | 76900 | 2 | 594, 595 |
| CTe | 76902 | 2 | 370, 371 |
| CTe | 76903 | 2 | 188, 189 |
| CTe | 76904 | 2 | 176, 177 |
| CTe | 76908 | 2 | 1039, 1040 |
| CTe | 78562 | 2 | 607, 608 |
| CTe | 78569 | 2 | 374, 375 |
| CTe | 78583 | 2 | 1079, 1080 |
| CTe | 78588 | 2 | 179, 180 |
| CTe | 78589 | 2 | 825, 826 |
| CTe | 78592 | 4 | 1030, 1031, 1032, 1033 |
| CTe | 78602 | 2 | 81, 82 |
| CTe | 78610 | 4 | 598, 599, 600, 601 |
| CTe | 78611 | 2 | 586, 587 |
| CTe | 78614 | 2 | 1051, 1052 |
| CTe | 78615 | 2 | 181, 182 |
| CTe | 78616 | 2 | 605, 606 |
| CTe | 78619 | 3 | 1087, 1088, 1089 |
| CTe | 78621 | 3 | 817, 818, 819 |
| CTe | 78623 | 3 | 91, 92, 93 |
| CTe | 78625 | 2 | 1045, 1046 |
| CTe | 78628 | 2 | 560, 561 |
| CTe | 78631 | 5 | 1058, 1059, 1060, 1061, 1062 |
| CTe | 78632 | 3 | 566, 567, 568 |
| CTe | 78635 | 2 | 359, 360 |
| CTe | 78644 | 3 | 172, 173, 174 |
| CTe | 78645 | 2 | 83, 84 |
| CTe | 78646 | 2 | 609, 610 |
| CTe | 78648 | 2 | 1020, 1021 |
| CTe | 78649 | 3 | 1063, 1064, 1065 |

## Duplicidades por CTe — Power Query

Não verificável: o arquivo tratado não possui a coluna CTe.

## Lista completa dos registros originalmente excedentes

| Linha | Nota Fiscal | CTe | Tipo CTe | Transportadora | Cancelamento | Emissão | Saída | Entrega | Valor Frete | Operação | Ocorr. NF | Ocorr. CTe | Cancelado | Devolução | Complementar | Reentrega | Redespacho | Possível motivo confirmado |
|---:|---|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---|---|---|---|
| 10 | 1015735 | 186678 | DEVOLUCAO | 01125797001945 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 | 2026-07-13 00:00:00 | 4973.55 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Destinatário e Tomador representam a mesma parte |
| 79 | 905330 | 663948 | DEVOLUCAO | 18233211007223 - SOLISTICA |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 |  | 125.55 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência |
| 381 | 907276 | 78654 | ENTREGA NORMAL | 12270745000400 - PVN - SUMARE |  | 2026-07-16 00:00:00 | 2026-07-16 00:00:00 |  | 84.45 |  | 1 | 1 | False | False | False | False | False | Fatura preenchida sem aprovação financeira |
| 382 | 11962 | 476205 | ENTREGA NORMAL | 20147617003400 - JAMEF TRANSPORTES LT |  | 2026-07-16 00:00:00 | 2026-07-16 00:00:00 | 2026-07-21 00:00:00 | 609.28 |  | 1 | 1 | False | False | False | False | False | Destinatário e Tomador representam a mesma parte |
| 778 | 1018718 | 88264 | DEVOLUCAO | 01125797001007 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 | 2026-07-16 00:00:00 |  | 70.95 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Destinatário e Tomador representam a mesma parte |
| 832 | 1014497 | 596465 | ENTREGA NORMAL | 87183570000142 - TRANSPORTADORA MINUANO |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 |  | 156.76 |  | 1 | 1 | False | True | False | False | False | Destinatário e Tomador representam a mesma parte |
| 833 | 1015940 | 596464 | ENTREGA NORMAL | 87183570000142 - TRANSPORTADORA MINUANO |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 |  | 69.45 |  | 1 | 1 | False | True | False | False | False | Destinatário e Tomador representam a mesma parte |
| 835 | 1005197 | 324025 | COMPLEMENTAR | 05112286000110 - BINHO |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 | 516.13 |  | 1 | 1 | False | False | True | False | False | Tipo CTe não pertence aos tipos mantidos pela referência |
| 836 | 1015404 | 156959 | DEVOLUCAO | 01125797003646 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 |  | 72.84 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Destinatário e Tomador representam a mesma parte |
| 1005 | 1009888 | 641216 | DEVOLUCAO | 01125797002593 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 | 2026-07-08 00:00:00 | 71.53 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Destinatário e Tomador representam a mesma parte |
| 1006 | 1011069 | 754988 | DEVOLUCAO | 01125797000892 - ATIVA LOGISTICA |  | 2026-07-16 00:00:00 | 2026-07-16 00:00:00 |  | 88.67 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Destinatário e Tomador representam a mesma parte |
| 1008 | 1014736 | 42502 | DEVOLUCAO | 05112286000463 - BINHO TRANSPORTES & LOGISTICA EIRELI |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 |  | 3146.42 |  | 1 | 1 | False | True | False | False | False | Tipo CTe não pertence aos tipos mantidos pela referência; Destinatário e Tomador representam a mesma parte |
| 1009 | 904895 | 445320 | DEVOLUCAO | 18233211001292 - FL BRASIL HOLDING, LOGISTICA E TRANSPORTE LTDA |  | 2026-07-15 00:00:00 | 2026-07-15 00:00:00 |  | 145.45 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência |
| 1091 | 226752 | 1756670 | ENTREGA NORMAL | 01125797000540 - ATIVA DISTR E LOGISTICA LTDA | 2026-07-16 13:41:30 | 2026-07-16 00:00:00 |  |  | 71.57 |  | 2 | 1 | True | False | False | False | True | Saída não preenchida |
| 1092 | 39276 | 374610 | ENTREGA NORMAL | 01125797003050 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 131.45 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1093 | 209 | 130883 | ENTREGA NORMAL | 14709618000210 - EXCARGO TRANSPORTE |  | 2026-07-15 00:00:00 |  |  | 23.9 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida |
| 1094 | 1013987 | 5934 | DEVOLUCAO | 05915821000171 - POTENZA TRANSPORTES LTDA |  | 2026-07-15 00:00:00 |  |  | 100 |  | 1 | 1 | False | True | False | False | False | Tipo CTe não pertence aos tipos mantidos pela referência; Saída não preenchida; Fatura preenchida sem aprovação financeira |
| 1095 | 39189 | 374584 | ENTREGA NORMAL | 01125797003050 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 1791.1 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1096 | 1017194 | 78604 | ENTREGA NORMAL | 12270745000400 - PVN - SUMARE |  | 2026-07-16 00:00:00 |  | 2026-07-17 00:00:00 | 70.42 |  | 1 | 1 | False | False | False | False | False | Saída não preenchida |
| 1097 | 1019765 | 130660 | ENTREGA NORMAL | 14709618000210 - EXCARGO TRANSPORTE | 2026-07-16 00:40:48 | 2026-07-15 00:00:00 |  |  | 1004.89 |  | 2 | 1 | True | False | False | False | True | Saída não preenchida |
| 1098 | 212 | 130881 | ENTREGA NORMAL | 14709618000210 - EXCARGO TRANSPORTE |  | 2026-07-15 00:00:00 |  |  | 21.16 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida |
| 1099 | 1083 | 309973 | DEVOLUCAO | 01125797001430 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 64.36 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1100 | 3471 | 755009 | DEVOLUCAO | 01125797000892 - ATIVA LOGISTICA |  | 2026-07-16 00:00:00 |  |  | 61.15 |  | 1 | 1 | False | True | False | False | True | Tipo CTe não pertence aos tipos mantidos pela referência; Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1101 | 39278 | 374609 | ENTREGA NORMAL | 01125797003050 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 131.45 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1102 | 39275 | 374611 | ENTREGA NORMAL | 01125797003050 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 89.31 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1103 | 39274 | 374606 | ENTREGA NORMAL | 01125797003050 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 73.95 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1104 | 1014508 | 2156917 | REENTREGA | 20147617006859 - Jamef Transportes Ltda - Osasco |  | 2026-07-15 00:00:00 |  | 2026-07-16 00:00:00 | 97.5 |  | 1 | 1 | False | False | False | True | False | Saída não preenchida |
| 1105 | 39277 | 374591 | ENTREGA NORMAL | 01125797003050 - ATIVA DISTR E LOGISTICA LTDA |  | 2026-07-16 00:00:00 |  |  | 77.12 |  | 1 | 1 | False | False | False | False | True | Saída não preenchida; Destinatário e Tomador representam a mesma parte |
| 1106 | 1016273 | 2920327 | ENTREGA NORMAL | 87183570000223 - TRANSPORTADORA MINUANO |  | 2026-07-16 00:00:00 |  | 2026-07-21 00:00:00 | 68.21 |  | 1 | 2 | False | False | False | False | True | Saída não preenchida |
| 1107 | 1019059 | 2920327 | ENTREGA NORMAL | 87183570000223 - TRANSPORTADORA MINUANO |  | 2026-07-16 00:00:00 |  | 2026-07-21 00:00:00 | 68.21 |  | 2 | 2 | False | False | False | False | True | Saída não preenchida |

## Conclusão

O conjunto foi reconciliado integralmente: os dois lados possuem a mesma quantidade e o mesmo multiconjunto de Notas Fiscais.

Nenhuma regra de Prazo, Prazo2, Situação, CNPJ, Código Cliente, Data ou Ano foi implementada nesta sprint.
