<#-- Копия base/login/error.ftl + запасная ссылка на сайт. Keycloak выводит «Назад в приложение»,
     только если знает клиента; на ошибках вроде «restart login cookie not found» он его не знает,
     и человек застревал. Сайт и Keycloak за одним gateway, поэтому адрес фронта это путь ресурсов темы до /auth/ (учитывает BASE_PATH). -->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=false; section>
    <#if section = "header">
        ${kcSanitize(msg("errorTitle"))?no_esc}
    <#elseif section = "form">
        <div id="kc-error-message">
            <p class="instruction">${kcSanitize(message.summary)?no_esc}</p>
            <#if traceId??>
                <p class="instruction" id="traceId">${msg("traceIdSupportMessage", traceId)}</p>
            </#if>
            <#if !(skipLink??) && client?? && client.baseUrl?has_content>
                <p><a id="backToApplication" class="fsp-back-link" href="${client.baseUrl}">${msg("backToApplication")}</a></p>
            <#else>
                <p><a id="backToApplication" class="fsp-back-link" href="${url.resourcesPath?keep_before("/auth/")}/">${msg("backToApplication")}</a></p>
            </#if>
        </div>
    </#if>
</@layout.registrationLayout>
