Проблемы баги которые нукжно решить.
1. Прик подклбючении по SSH, у нас есть функция когда мы мождем просто навестить мышкой на текстовой документ yml txt py и так далее и у нас должно открываться окно с редлактором если стоит галочка в настройках терминала. 1 - проблема при наведении оно не точно показывает что ты хочешь открыть и открывает вообще не то, некоторые открывает не котоыре нет не понятно почему. 2 - проблема если мы возьмем окно мышкой и перетащим и в этот момент отпустим то у нас с страницы пропадает обсалютно все пока мы ее не перезагрузим. При открытии редлактора такая ошибка в консоли - Warning: Invalid values for props `data-undo`, `data-redo` on <div> tag. Either remove them from the element, or pass a string or number value to keep them in the DOM. For details, see https://reactjs.org/link/attribute-behavior 
    at div
    at CodeEditor (http://localhost:8080/src/components/editor/CodeEditor.tsx:172:30)
    at div
    at div
    at FileEditorModal (http://localhost:8080/src/components/editor/FileEditorModal.tsx?t=1783594250185:33:35)
    at div
    at TerminalPage (http://localhost:8080/src/pages/TerminalPage.tsx?t=1783594250185:27:17)
    at FeatureGate (http://localhost:8080/src/App.tsx?t=1783594354211:231:24)
    at RenderedRoute (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3329:8)
    at Outlet (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3700:25)
    at main
    at div
    at div
    at div
    at Provider (http://localhost:8080/node_modules/.vite/deps/dist-ItifKaiy.js?v=ffe4fb3d:33:12)
    at TooltipProvider (http://localhost:8080/node_modules/.vite/deps/@radix-ui_react-tooltip.js?v=ffe4fb3d:25:10)
    at http://localhost:8080/src/components/ui/sidebar/context.tsx:20:59
    at AppLayout (http://localhost:8080/src/components/AppLayout.tsx?t=1783594250185:40:19)
    at AuthGate (http://localhost:8080/src/App.tsx?t=1783594354211:129:21)
    at RenderedRoute (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3329:8)
    at Routes (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3772:8)
    at Suspense
    at Router (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3720:18)
    at BrowserRouter (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:4395:8)
    at Provider (http://localhost:8080/node_modules/.vite/deps/dist-ItifKaiy.js?v=ffe4fb3d:33:12)
    at TooltipProvider (http://localhost:8080/node_modules/.vite/deps/@radix-ui_react-tooltip.js?v=ffe4fb3d:25:10)
    at I18nProvider (http://localhost:8080/src/lib/i18n.tsx:33:32)
    at QueryClientProvider (http://localhost:8080/node_modules/.vite/deps/@tanstack_react-query.js?v=ffe4fb3d:2369:30)
    at App 

    а если мы перетаскиваем как я ранее говорил то еще такая ошитбка появляется - Uncaught TypeError: Cannot read properties of null (reading 'origX')
    at FileEditorModal.tsx:111:51
    at basicStateReducer (react-dom-BRJs3cXW.js?v=ffe4fb3d:9745:42)
    at updateReducer (react-dom-BRJs3cXW.js?v=ffe4fb3d:9821:19)
    at updateState (react-dom-BRJs3cXW.js?v=ffe4fb3d:9993:11)
    at Object.useState (react-dom-BRJs3cXW.js?v=ffe4fb3d:10639:13)
    at useState (react.js?v=ffe4fb3d:963:31)
    at FileEditorModal (FileEditorModal.tsx:89:27)
    at renderWithHooks (react-dom-BRJs3cXW.js?v=ffe4fb3d:9632:19)
    at updateFunctionComponent (react-dom-BRJs3cXW.js?v=ffe4fb3d:12122:19)
    at beginWork (react-dom-BRJs3cXW.js?v=ffe4fb3d:13096:13)
(анонимная) @ FileEditorModal.tsx:111
basicStateReducer @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9745
updateReducer @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9821
updateState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9993
useState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10639
useState @ react.js?v=ffe4fb3d:963
(анонимная) @ FileEditorModal.tsx:89
renderWithHooks @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9632
updateFunctionComponent @ react-dom-BRJs3cXW.js?v=ffe4fb3d:12122
beginWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:13096
callCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:3142
invokeGuardedCallbackDev @ react-dom-BRJs3cXW.js?v=ffe4fb3d:3162
invokeGuardedCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:3201
beginWork$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15990
performUnitOfWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15568
workLoopSync @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15517
renderRootSync @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15500
performConcurrentWorkOnRoot @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15140
workLoop @ react-dom-BRJs3cXW.js?v=ffe4fb3d:172
flushWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:155
performWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:331
postMessage
schedulePerformWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:350
requestHostCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:359
unstable_scheduleCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:285
scheduleCallback$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:16031
ensureRootIsScheduled @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15124
scheduleUpdateOnFiber @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15061
dispatchSetState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10297
(анонимная) @ FileEditorModal.tsx:111
FileEditorModal.tsx:111 Uncaught TypeError: Cannot read properties of null (reading 'origX')
    at FileEditorModal.tsx:111:51
    at basicStateReducer (react-dom-BRJs3cXW.js?v=ffe4fb3d:9745:42)
    at updateReducer (react-dom-BRJs3cXW.js?v=ffe4fb3d:9821:19)
    at updateState (react-dom-BRJs3cXW.js?v=ffe4fb3d:9993:11)
    at Object.useState (react-dom-BRJs3cXW.js?v=ffe4fb3d:10639:13)
    at useState (react.js?v=ffe4fb3d:963:31)
    at FileEditorModal (FileEditorModal.tsx:89:27)
    at renderWithHooks (react-dom-BRJs3cXW.js?v=ffe4fb3d:9632:19)
    at updateFunctionComponent (react-dom-BRJs3cXW.js?v=ffe4fb3d:12122:19)
    at beginWork (react-dom-BRJs3cXW.js?v=ffe4fb3d:13096:13)
(анонимная) @ FileEditorModal.tsx:111
basicStateReducer @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9745
updateReducer @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9821
updateState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9993
useState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10639
useState @ react.js?v=ffe4fb3d:963
(анонимная) @ FileEditorModal.tsx:89
renderWithHooks @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9632
updateFunctionComponent @ react-dom-BRJs3cXW.js?v=ffe4fb3d:12122
beginWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:13096
callCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:3142
invokeGuardedCallbackDev @ react-dom-BRJs3cXW.js?v=ffe4fb3d:3162
invokeGuardedCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:3201
beginWork$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15990
performUnitOfWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15568
workLoopSync @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15517
renderRootSync @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15500
recoverFromConcurrentError @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15193
performConcurrentWorkOnRoot @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15146
workLoop @ react-dom-BRJs3cXW.js?v=ffe4fb3d:172
flushWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:155
performWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:331
postMessage
schedulePerformWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:350
requestHostCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:359
unstable_scheduleCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:285
scheduleCallback$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:16031
ensureRootIsScheduled @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15124
scheduleUpdateOnFiber @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15061
dispatchSetState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10297
(анонимная) @ FileEditorModal.tsx:111
react-dom-BRJs3cXW.js?v=ffe4fb3d:11719 The above error occurred in the <FileEditorModal> component:

    at FileEditorModal (http://localhost:8080/src/components/editor/FileEditorModal.tsx?t=1783594250185:33:35)
    at div
    at TerminalPage (http://localhost:8080/src/pages/TerminalPage.tsx?t=1783594250185:27:17)
    at FeatureGate (http://localhost:8080/src/App.tsx?t=1783594354211:231:24)
    at RenderedRoute (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3329:8)
    at Outlet (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3700:25)
    at main
    at div
    at div
    at div
    at Provider (http://localhost:8080/node_modules/.vite/deps/dist-ItifKaiy.js?v=ffe4fb3d:33:12)
    at TooltipProvider (http://localhost:8080/node_modules/.vite/deps/@radix-ui_react-tooltip.js?v=ffe4fb3d:25:10)
    at http://localhost:8080/src/components/ui/sidebar/context.tsx:20:59
    at AppLayout (http://localhost:8080/src/components/AppLayout.tsx?t=1783594250185:40:19)
    at AuthGate (http://localhost:8080/src/App.tsx?t=1783594354211:129:21)
    at RenderedRoute (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3329:8)
    at Routes (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3772:8)
    at Suspense
    at Router (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:3720:18)
    at BrowserRouter (http://localhost:8080/node_modules/.vite/deps/react-router-dom.js?v=ffe4fb3d:4395:8)
    at Provider (http://localhost:8080/node_modules/.vite/deps/dist-ItifKaiy.js?v=ffe4fb3d:33:12)
    at TooltipProvider (http://localhost:8080/node_modules/.vite/deps/@radix-ui_react-tooltip.js?v=ffe4fb3d:25:10)
    at I18nProvider (http://localhost:8080/src/lib/i18n.tsx:33:32)
    at QueryClientProvider (http://localhost:8080/node_modules/.vite/deps/@tanstack_react-query.js?v=ffe4fb3d:2369:30)
    at App

Consider adding an error boundary to your tree to customize error handling behavior.
Visit https://reactjs.org/link/error-boundaries to learn more about error boundaries.
logCapturedError @ react-dom-BRJs3cXW.js?v=ffe4fb3d:11719
update.callback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:11734
callCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9416
commitUpdateQueue @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9432
commitLayoutEffectOnFiber @ react-dom-BRJs3cXW.js?v=ffe4fb3d:13930
commitLayoutMountEffects_complete @ react-dom-BRJs3cXW.js?v=ffe4fb3d:14598
commitLayoutEffects_begin @ react-dom-BRJs3cXW.js?v=ffe4fb3d:14588
commitLayoutEffects @ react-dom-BRJs3cXW.js?v=ffe4fb3d:14547
commitRootImpl @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15697
commitRoot @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15639
finishConcurrentRender @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15210
performConcurrentWorkOnRoot @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15179
workLoop @ react-dom-BRJs3cXW.js?v=ffe4fb3d:172
flushWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:155
performWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:331
postMessage
schedulePerformWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:350
requestHostCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:359
unstable_scheduleCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:285
scheduleCallback$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:16031
ensureRootIsScheduled @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15124
scheduleUpdateOnFiber @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15061
dispatchSetState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10297
(анонимная) @ FileEditorModal.tsx:111
react-dom-BRJs3cXW.js?v=ffe4fb3d:15739 Uncaught TypeError: Cannot read properties of null (reading 'origX')
    at FileEditorModal.tsx:111:51
    at basicStateReducer (react-dom-BRJs3cXW.js?v=ffe4fb3d:9745:42)
    at updateReducer (react-dom-BRJs3cXW.js?v=ffe4fb3d:9821:19)
    at updateState (react-dom-BRJs3cXW.js?v=ffe4fb3d:9993:11)
    at Object.useState (react-dom-BRJs3cXW.js?v=ffe4fb3d:10639:13)
    at useState (react.js?v=ffe4fb3d:963:31)
    at FileEditorModal (FileEditorModal.tsx:89:27)
    at renderWithHooks (react-dom-BRJs3cXW.js?v=ffe4fb3d:9632:19)
    at updateFunctionComponent (react-dom-BRJs3cXW.js?v=ffe4fb3d:12122:19)
    at beginWork (react-dom-BRJs3cXW.js?v=ffe4fb3d:13096:13)
(анонимная) @ FileEditorModal.tsx:111
basicStateReducer @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9745
updateReducer @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9821
updateState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9993
useState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10639
useState @ react.js?v=ffe4fb3d:963
(анонимная) @ FileEditorModal.tsx:89
renderWithHooks @ react-dom-BRJs3cXW.js?v=ffe4fb3d:9632
updateFunctionComponent @ react-dom-BRJs3cXW.js?v=ffe4fb3d:12122
beginWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:13096
beginWork$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15982
performUnitOfWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15568
workLoopSync @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15517
renderRootSync @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15500
recoverFromConcurrentError @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15193
performConcurrentWorkOnRoot @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15146
workLoop @ react-dom-BRJs3cXW.js?v=ffe4fb3d:172
flushWork @ react-dom-BRJs3cXW.js?v=ffe4fb3d:155
performWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:331
postMessage
schedulePerformWorkUntilDeadline @ react-dom-BRJs3cXW.js?v=ffe4fb3d:350
requestHostCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:359
unstable_scheduleCallback @ react-dom-BRJs3cXW.js?v=ffe4fb3d:285
scheduleCallback$1 @ react-dom-BRJs3cXW.js?v=ffe4fb3d:16031
ensureRootIsScheduled @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15124
scheduleUpdateOnFiber @ react-dom-BRJs3cXW.js?v=ffe4fb3d:15061
dispatchSetState @ react-dom-BRJs3cXW.js?v=ffe4fb3d:10297
(анонимная) @ FileEditorModal.tsx:111




2- Когда мы открываем редактор GUI у нас если есть вомзжность то мы открываем от админа так как бывает что документы без админ sudo прав не открывается, а так же если мы редактируем файл и после закрывает модальное окно с предупреждением что файл не сохарянен должно вылазит по верх всех окно в том числе и редактируемо GUI редактора.

3 - Если мы открыли докумен просто через USER и после не можем сохранить без админ прав нужно предложить пользователью вписать пароль что бы были админские права sudo  файл должен сохарниться. Нужно придумать как это реализовать. Сначала напишем план. 