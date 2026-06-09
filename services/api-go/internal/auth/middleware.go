package auth

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

const (
	ContextUserIDKey = "auth.user_id"
	ContextEmailKey  = "auth.email"
	ContextRoleKey   = "auth.role"
)

func AuthMiddleware(authenticator Authenticator) gin.HandlerFunc {
	return func(c *gin.Context) {
		user, err := authenticator.AuthenticateBearer(c.Request.Context(), c.GetHeader("Authorization"))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error":   "unauthorized",
				"message": "请先登录",
			})
			return
		}

		c.Set(ContextUserIDKey, user.ID)
		c.Set(ContextEmailKey, user.Email)
		c.Set(ContextRoleKey, user.Role)
		c.Next()
	}
}

func CurrentUserID(c *gin.Context) string {
	value, ok := c.Get(ContextUserIDKey)
	if !ok {
		return ""
	}

	userID, _ := value.(string)
	return userID
}

func CurrentRole(c *gin.Context) string {
	value, ok := c.Get(ContextRoleKey)
	if !ok {
		return ""
	}

	role, _ := value.(string)
	return role
}

func RequireRoles(allowedRoles ...string) gin.HandlerFunc {
	allowed := map[string]struct{}{}
	for _, role := range allowedRoles {
		allowed[role] = struct{}{}
	}

	return func(c *gin.Context) {
		role := CurrentRole(c)
		if _, ok := allowed[role]; !ok {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{
				"error":   "forbidden",
				"message": "当前账号没有权限执行该操作",
			})
			return
		}

		c.Next()
	}
}
