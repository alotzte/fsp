<#-- Копия base/login/info.ftl + запасная ссылка на сайт, если Keycloak не знает, куда вернуть
     (см. комментарий в error.ftl). -->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=false; section>
    <#if section = "header">
        <#if messageHeader??>
            ${kcSanitize(msg("${messageHeader}"))?no_esc}
        <#else>
            ${message.summary}
        </#if>
    <#elseif section = "form">
    <div id="kc-info-message">
        <p class="instruction">${message.summary}<#if requiredActions??><#list requiredActions>: <b><#items as reqActionItem>${kcSanitize(msg("requiredAction.${reqActionItem}"))?no_esc}<#sep>, </#items></b></#list><#else></#if></p>
        <#if !(skipLink??) && pageRedirectUri?has_content>
            <p><a class="fsp-back-link" href="${pageRedirectUri}">${msg("backToApplication")}</a></p>
        <#elseif !(skipLink??) && actionUri?has_content>
            <p><a class="fsp-back-link" href="${actionUri}">${msg("proceedWithAction")}</a></p>
        <#elseif !(skipLink??) && (client.baseUrl)?has_content>
            <p><a class="fsp-back-link" href="${client.baseUrl}">${msg("backToApplication")}</a></p>
        <#else>
            <p><a class="fsp-back-link" href="${url.resourcesPath?keep_before("/auth/")}/">${msg("backToApplication")}</a></p>
        </#if>
    </div>
    </#if>
</@layout.registrationLayout>
